"""Track B subgoal selector: language instruction → goal image.

How Track B differs from Track A
──────────────────────────────────
Track A: we are given the goal image directly (e.g. "here is a photo of the
         destination — navigate to where this was taken").

Track B: we are given a LANGUAGE instruction ("Walk past the sofa and stop at
         the fridge").  GNM can only navigate to images, not words.

The subgoal selector bridges this gap:
  1. Build a topological map of the scene: a graph of keyframe images
     taken at regular intervals along known paths.
  2. Embed each keyframe image AND the language instruction into a shared
     vision-language space (using a CLIP model).
  3. Find the keyframe most similar to the instruction → this is the subgoal.
  4. Give that keyframe image to GNM as the goal.

Why CLIP?
  CLIP (Contrastive Language-Image Pretraining) was trained to align text
  and image embeddings.  Given "a photo of a fridge", it returns a vector
  close to actual fridge photos.  This lets us do text→image retrieval.

Fallback
  If CLIP is not available, we fall back to using the LAST keyframe of the
  trajectory as the goal (same as Track A).  This is the "oracle" baseline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SubgoalSelector:
    """Select a subgoal image from a topological map using text-image retrieval.

    Parameters
    ----------
    keyframes : list of (H, W, 3) uint8 arrays
        Images from the topological map, in order.
    keyframe_positions : list of (x, y) tuples
        World positions corresponding to each keyframe.
    device : str
        "cuda" or "cpu"
    model_name : str
        CLIP variant to use.  Default: "openai/clip-vit-base-patch16"
    """

    def __init__(
        self,
        keyframes: list[np.ndarray],
        keyframe_positions: list[tuple[float, float]],
        device: str = "cpu",
        model_name: str = "openai/clip-vit-base-patch16",
    ) -> None:
        self.keyframes          = keyframes
        self.keyframe_positions = keyframe_positions
        self.device             = device
        self._clip_model        = None
        self._clip_processor    = None
        self._keyframe_embeds: Optional[np.ndarray] = None

        self._load_clip(model_name)
        if self._clip_model is not None:
            self._embed_keyframes()

    def _load_clip(self, model_name: str) -> None:
        try:
            from transformers import CLIPModel, CLIPProcessor
            self._clip_model     = CLIPModel.from_pretrained(model_name)
            self._clip_processor = CLIPProcessor.from_pretrained(model_name)
            self._clip_model.eval()
            logger.info(f"CLIP loaded: {model_name}")
        except ImportError:
            logger.warning(
                "transformers not installed — Track B will use oracle fallback. "
                "Install with: pip install transformers"
            )
        except Exception as e:
            logger.warning(f"CLIP load failed ({e}) — using oracle fallback")

    def _embed_keyframes(self) -> None:
        """Pre-compute CLIP image embeddings for all keyframes."""
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
        logger.info(f"Embedded {len(self.keyframes)} keyframes")

    def select(self, instruction: str) -> tuple[np.ndarray, tuple[float, float], int]:
        """Select the best subgoal image for a language instruction.

        Parameters
        ----------
        instruction : str
            Navigation instruction, e.g. "Walk to the nurse station on the left"

        Returns
        -------
        goal_image    : (H, W, 3) uint8
        goal_position : (x, y) world coordinates
        goal_idx      : index into self.keyframes
        """
        if self._clip_model is None or self._keyframe_embeds is None:
            # Oracle fallback: use last keyframe
            logger.debug("CLIP not available — using oracle (last keyframe)")
            idx = len(self.keyframes) - 1
            return self.keyframes[idx], self.keyframe_positions[idx], idx

        import torch

        # Embed the instruction
        inputs = self._clip_processor(
            text=[instruction], return_tensors="pt", padding=True
        )
        with torch.no_grad():
            text_feat = self._clip_model.get_text_features(**inputs)
            text_feat = text_feat / text_feat.norm(dim=-1, keepdim=True)

        text_np = text_feat.cpu().numpy()  # (1, D)

        # Cosine similarity with all keyframes
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

        traj_dir = Path(traj_dir)
        data     = pickle.load(open(traj_dir / "traj_data.pkl", "rb"))
        positions = data["position"]
        T         = len(positions)

        keyframes = []
        positions_out = []
        for t in range(0, T, stride):
            img_path = traj_dir / f"{t}.jpg"
            if img_path.exists():
                img = cv2.imread(str(img_path))
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                keyframes.append(img)
                positions_out.append(tuple(positions[t].tolist()))

        logger.info(f"Built topological map: {len(keyframes)} keyframes from {traj_dir.name}")
        return cls(keyframes=keyframes, keyframe_positions=positions_out, **kwargs)
