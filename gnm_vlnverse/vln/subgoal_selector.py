"""Track B subgoal selector: language instruction → goal image.

How Track B differs from Track A
──────────────────────────────────
Track A: the goal image is provided directly.

Track B: a LANGUAGE instruction is provided ("Walk past the sofa and stop at
         the fridge").  GNM can only navigate to images, not words.

The subgoal selector bridges this gap:
  1. Build a topological map of the scene: keyframe images sampled at
     regular intervals along known reference paths.
  2. Embed each keyframe image AND the language instruction into a shared
     vision-language space using a CLIP model.
  3. Select the keyframe with the highest cosine similarity to the instruction.
  4. Give that keyframe image to GNM as the visual goal.

Why CLIP?
  CLIP (Contrastive Language-Image Pretraining) aligns text and image
  embeddings.  Given "a photo of a fridge", its output vector is close to
  actual fridge images, enabling text-to-image retrieval.

Encoder availability
  CLIP requires the optional `language` dependency group:
      pip install 'gnm-vlnverse[language]'

  If CLIP is not loaded, select() raises EncoderUnavailable.
  The caller must handle this explicitly — the selector never silently
  substitutes the final frame when the encoder is absent or fails.

Reproducibility attributes
  Available via SubgoalSelector.clip_info() when CLIP is loaded.
  Records model identifier, revision, embedding dimension, and
  normalisation status.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Install command displayed in error messages
_INSTALL_CMD = "pip install 'gnm-vlnverse[language]'"


class EncoderUnavailable(RuntimeError):
    """Raised when the CLIP encoder is not loaded and select() is called.

    Attributes
    ----------
    reason : str
        Machine-readable reason code.  Always "ENCODER_UNAVAILABLE".
    message : str
        Human-readable explanation including the install command.
    """

    reason: str = "ENCODER_UNAVAILABLE"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class SubgoalSelector:
    """Select a subgoal image from a topological map using CLIP text-image retrieval.

    Parameters
    ----------
    keyframes : list of (H, W, 3) uint8 arrays
        Ordered keyframe images from the topological map.
    keyframe_positions : list of (x, y) tuples
        World-coordinate positions corresponding to each keyframe.
    device : str
        Device for CLIP inference.  "cpu" or "cuda".
    model_name : str
        HuggingFace CLIP model identifier.
        Default: "openai/clip-vit-base-patch16"
    load_clip : bool
        If True (default), attempt to load CLIP on construction.
        Set False when building a selector purely for non-CLIP methods.
    """

    def __init__(
        self,
        keyframes: list[np.ndarray],
        keyframe_positions: list[tuple[float, float]],
        device: str = "cpu",
        model_name: str = "openai/clip-vit-base-patch16",
        load_clip: bool = True,
    ) -> None:
        if len(keyframes) != len(keyframe_positions):
            raise ValueError(
                f"keyframes ({len(keyframes)}) and keyframe_positions "
                f"({len(keyframe_positions)}) must have equal length."
            )
        self.keyframes           = keyframes
        self.keyframe_positions  = keyframe_positions
        self.device              = device
        self._model_name         = model_name
        self._clip_model         = None
        self._clip_processor     = None
        self._clip_revision: Optional[str]  = None
        self._embed_dim:     Optional[int]  = None
        self._keyframe_embeds: Optional[np.ndarray] = None

        if load_clip:
            self._load_clip(model_name)
            if self._clip_model is not None:
                self._embed_keyframes()

    # ── CLIP loading ──────────────────────────────────────────────────────────

    def _load_clip(self, model_name: str) -> None:
        """Attempt to load CLIP.  Sets _clip_model to None on any failure."""
        try:
            from transformers import CLIPModel, CLIPProcessor
            self._clip_model     = CLIPModel.from_pretrained(model_name)
            self._clip_processor = CLIPProcessor.from_pretrained(model_name)
            self._clip_model.eval()
            cfg = getattr(self._clip_model, "config", None)
            self._clip_revision = getattr(cfg, "_name_or_path", model_name)
            logger.info(f"CLIP loaded: {model_name}")
        except ImportError:
            logger.warning(
                f"transformers not installed — CLIP unavailable. "
                f"Install with: {_INSTALL_CMD}"
            )
        except Exception as exc:
            logger.warning(f"CLIP load failed ({exc!r}) — encoder unavailable")

    def _embed_keyframes(self) -> None:
        """Pre-compute and L2-normalise CLIP image embeddings for all keyframes."""
        import torch
        from PIL import Image

        all_embeds = []
        batch_size = 32
        for i in range(0, len(self.keyframes), batch_size):
            batch = self.keyframes[i : i + batch_size]
            pil_images = [Image.fromarray(f) for f in batch]
            inputs = self._clip_processor(images=pil_images, return_tensors="pt")
            with torch.no_grad():
                feats = self._clip_model.get_image_features(**inputs)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            all_embeds.append(feats.cpu().numpy())

        self._keyframe_embeds = np.concatenate(all_embeds, axis=0)
        self._embed_dim = self._keyframe_embeds.shape[1]
        logger.info(f"Embedded {len(self.keyframes)} keyframes  dim={self._embed_dim}")

    # ── Reproducibility info ──────────────────────────────────────────────────

    def clip_info(self) -> dict:
        """Return a dictionary of CLIP reproducibility attributes.

        Returns a dict with status="ENCODER_UNAVAILABLE" when CLIP is not loaded.
        """
        if self._clip_model is None:
            return {
                "status":              "ENCODER_UNAVAILABLE",
                "reason":              f"transformers not installed. Install: {_INSTALL_CMD}",
                "model_identifier":    self._model_name,
                "model_revision":      None,
                "embedding_dim":       None,
                "embedding_normalised": True,
                "device":              self.device,
                "image_stride":        None,
            }
        return {
            "status":              "LOADED",
            "model_identifier":    self._model_name,
            "model_revision":      self._clip_revision,
            "embedding_dim":       self._embed_dim,
            "embedding_normalised": True,
            "device":              self.device,
            "n_keyframes_embedded": len(self.keyframes),
        }

    # ── Subgoal selection ─────────────────────────────────────────────────────

    def select(self, instruction: str) -> tuple[np.ndarray, tuple[float, float], int]:
        """Select the best subgoal image for a language instruction using CLIP.

        Parameters
        ----------
        instruction : str
            Navigation instruction, e.g. "Walk to the nurse station on the left"

        Returns
        -------
        goal_image    : (H, W, 3) uint8
        goal_position : (x, y) world coordinates
        goal_idx      : index into self.keyframes

        Raises
        ------
        EncoderUnavailable
            If CLIP was not successfully loaded.  The caller must handle this
            explicitly.  This method never silently substitutes the final frame.
        """
        if self._clip_model is None or self._keyframe_embeds is None:
            raise EncoderUnavailable(
                f"ENCODER_UNAVAILABLE: CLIP model '{self._model_name}' is not loaded. "
                f"Install the language dependency group: {_INSTALL_CMD}"
            )

        import torch

        inputs = self._clip_processor(
            text=[instruction], return_tensors="pt", padding=True
        )
        with torch.no_grad():
            text_feat = self._clip_model.get_text_features(**inputs)
            text_feat = text_feat / text_feat.norm(dim=-1, keepdim=True)

        text_np = text_feat.cpu().numpy()           # (1, D)
        similarities = (self._keyframe_embeds @ text_np.T).squeeze()  # (N,)
        best_idx     = int(np.argmax(similarities))
        best_score   = float(similarities[best_idx])

        logger.debug(
            f"Subgoal selected: idx={best_idx}  sim={best_score:.3f}  "
            f"pos={self.keyframe_positions[best_idx]}"
        )

        return (
            self.keyframes[best_idx],
            self.keyframe_positions[best_idx],
            best_idx,
        )

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def from_language_episode(
        cls,
        episode: "LanguageEpisode",  # gnm_vlnverse.vln.language_episode.LanguageEpisode
        **kwargs,
    ) -> "SubgoalSelector":
        """Build selector directly from a LanguageEpisode (no re-loading from disk)."""
        return cls(
            keyframes=episode.keyframes,
            keyframe_positions=episode.positions,
            **kwargs,
        )

    @classmethod
    def from_trajectory(
        cls,
        traj_dir: Path | str,
        stride: int = 5,
        **kwargs,
    ) -> "SubgoalSelector":
        """Build selector from a GNM-format trajectory directory.

        Parameters
        ----------
        traj_dir : Path
            Directory containing 0.jpg, 1.jpg, ... and traj_data.pkl
        stride : int
            Sample every Nth frame for the topological map.  Default: 5
        """
        import pickle
        import cv2

        traj_dir  = Path(traj_dir)
        data      = pickle.load(open(traj_dir / "traj_data.pkl", "rb"))
        positions = data["position"]
        T         = len(positions)

        keyframes:     list[np.ndarray]          = []
        positions_out: list[tuple[float, float]] = []
        for t in range(0, T, stride):
            img_path = traj_dir / f"{t}.jpg"
            if img_path.exists():
                img = cv2.imread(str(img_path))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                keyframes.append(img)
                positions_out.append(tuple(positions[t].tolist()))

        logger.info(f"Built topological map: {len(keyframes)} keyframes from {traj_dir.name}")
        return cls(keyframes=keyframes, keyframe_positions=positions_out, **kwargs)
