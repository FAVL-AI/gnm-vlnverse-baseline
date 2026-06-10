"""
hdf5_episode_recorder.py — Extended HDF5 episode recorder for FleetSafe.

Implements Schema B: the extended raw HDF5 format that stores everything
needed for both GNM reproduction and FleetSafe analysis.

HDF5 layout (one file per episode):

    /meta
        robot_name          str  "yahboom_m3pro"
        platform            str  "jetson_orin_nx" | "isaac_sim" | "mujoco"
        environment         str  "hospital_corridor" | ...
        camera_frame        str  "usb_cam" | "isaac_camera"
        session_id          str  ISO timestamp
        fleetsafe_enabled   bool
        model_name          str  "gnm" | "vint" | "nomad"

    /time
        timestamps_ns       int64  [T]   nanoseconds since Unix epoch

    /obs
        rgb                 uint8  [T, H, W, 3]   egocentric forward camera
        depth               float32 [T, H, W]     (optional, NaN if absent)

    /state
        position            float32 [T, 2]  x,y metres (from odometry)
        yaw                 float32 [T]     heading radians
        linear_velocity     float32 [T, 3]  vx,vy,vz m/s
        angular_velocity    float32 [T, 3]  wx,wy,wz rad/s

    /actions
        cmd_vel             float32 [T, 3]  vx,vy,wz (what was sent to robot)
        u_nom               float32 [T, 3]  GNM/ViNT nominal command
        u_safe              float32 [T, 3]  FleetSafe safe command

    /safety
        min_dist_m          float32 [T]   min obstacle surface distance
        cbf_active          bool    [T]   True when CBF modified u_nom
        estop_triggered     bool    [T]   True when E-STOP fired
        h_min               float32 [T]   minimum barrier value h_i(x)

    /goals
        goal_rgb            uint8  [H, W, 3]  single goal image (for this episode)
        goal_position       float32 [2]        goal x,y if known

The /obs/rgb and /state/position,yaw entries are all that GNM training needs.
All other groups support FleetSafe analysis and future research extensions.

Usage
-----
    recorder = HDF5EpisodeRecorder(
        output_dir="data/hdf5_episodes",
        env_name="hospital_corridor",
        platform="isaac_sim",
        model_name="gnm",
        fleetsafe=True,
        image_size=(85, 64),
    )

    # Per step:
    recorder.record_step(
        rgb_img    = pil_image,
        position   = np.array([x, y]),
        yaw        = yaw,
        u_nom      = np.array([raw_vx, 0.0, raw_wz]),
        u_safe     = np.array([safe_vx, 0.0, safe_wz]),
        cbf_active = intervened,
        min_dist_m = min_d,
    )

    # End of episode:
    path = recorder.save(goal_img=goal_pil_image)
    print(f"Saved: {path}")
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from PIL import Image as PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import h5py
    _H5_OK = True
except ImportError:
    _H5_OK = False


class HDF5EpisodeRecorder:
    """
    Records one navigation episode into an HDF5 file.

    All arrays are accumulated in memory and flushed to disk once at the
    end of the episode.  This avoids per-step HDF5 overhead.

    If h5py is not installed, falls back to a numpy .npz bundle.
    """

    def __init__(
        self,
        output_dir:   str | Path,
        env_name:     str  = "unknown",
        platform:     str  = "isaac_sim",
        model_name:   str  = "gnm",
        camera_frame: str  = "isaac_camera",
        fleetsafe:    bool = True,
        image_size:   tuple[int, int] = (85, 64),
    ) -> None:
        self._output_dir  = Path(output_dir)
        self._env_name    = env_name
        self._platform    = platform
        self._model_name  = model_name
        self._camera_frame = camera_frame
        self._fleetsafe   = fleetsafe
        self._W, self._H  = image_size
        self._session_id  = time.strftime("%Y%m%dT%H%M%S")

        # Per-step buffers
        self._timestamps:    list[int]   = []
        self._rgb:           list        = []   # (H,W,3) uint8
        self._depth:         list        = []   # (H,W) float32 or None
        self._position:      list        = []   # [x,y]
        self._yaw:           list        = []
        self._lin_vel:       list        = []   # [vx,vy,vz]
        self._ang_vel:       list        = []   # [wx,wy,wz]
        self._cmd_vel:       list        = []   # [vx,vy,wz]
        self._u_nom:         list        = []
        self._u_safe:        list        = []
        self._min_dist:      list        = []
        self._cbf_active:    list        = []
        self._estop:         list        = []
        self._h_min:         list        = []

    # ── Per-step recording ────────────────────────────────────────────────────

    def record_step(
        self,
        rgb_img:     "PILImage.Image | np.ndarray",
        position:    np.ndarray,
        yaw:         float,
        u_nom:       Optional[np.ndarray] = None,
        u_safe:      Optional[np.ndarray] = None,
        cmd_vel:     Optional[np.ndarray] = None,
        depth_img:   Optional[np.ndarray] = None,
        lin_vel:     Optional[np.ndarray] = None,
        ang_vel:     Optional[np.ndarray] = None,
        cbf_active:  bool  = False,
        estop:       bool  = False,
        min_dist_m:  float = float("nan"),
        h_min:       float = float("nan"),
        timestamp_ns: Optional[int] = None,
    ) -> None:
        """Append one time step to the episode buffers."""
        ts = timestamp_ns if timestamp_ns is not None else int(time.time_ns())
        self._timestamps.append(ts)

        # RGB image
        if _PIL_OK and hasattr(rgb_img, "resize"):
            rgb_img = rgb_img.resize((self._W, self._H), PILImage.BILINEAR)
            arr = np.array(rgb_img, dtype=np.uint8)
        else:
            arr = np.asarray(rgb_img, dtype=np.uint8)
            if arr.shape[:2] != (self._H, self._W):
                # numpy-only resize (nearest neighbour)
                from PIL import Image as _PIL
                arr = np.array(_PIL.fromarray(arr).resize((self._W, self._H)))
        self._rgb.append(arr)

        # Optional depth
        if depth_img is not None:
            self._depth.append(np.asarray(depth_img, dtype=np.float32))
        else:
            self._depth.append(None)

        # State
        pos = np.asarray(position, dtype=np.float32).ravel()[:2]
        self._position.append(pos)
        self._yaw.append(float(yaw))

        lv = np.asarray(lin_vel, dtype=np.float32) if lin_vel is not None else np.zeros(3, np.float32)
        av = np.asarray(ang_vel, dtype=np.float32) if ang_vel is not None else np.zeros(3, np.float32)
        self._lin_vel.append(lv.ravel()[:3])
        self._ang_vel.append(av.ravel()[:3])

        # Actions
        un = np.asarray(u_nom,  dtype=np.float32) if u_nom  is not None else np.zeros(3, np.float32)
        us = np.asarray(u_safe, dtype=np.float32) if u_safe is not None else un.copy()
        cv = np.asarray(cmd_vel, dtype=np.float32) if cmd_vel is not None else us.copy()
        self._u_nom.append(un.ravel()[:3])
        self._u_safe.append(us.ravel()[:3])
        self._cmd_vel.append(cv.ravel()[:3])

        # Safety
        self._min_dist.append(float(min_dist_m))
        self._cbf_active.append(bool(cbf_active))
        self._estop.append(bool(estop))
        self._h_min.append(float(h_min))

    def set_goal_image(self, goal_img: "PILImage.Image | np.ndarray") -> None:
        """Store the goal image for this episode."""
        if _PIL_OK and hasattr(goal_img, "resize"):
            goal_img = goal_img.resize((self._W, self._H), PILImage.BILINEAR)
            self._goal_rgb: Optional[np.ndarray] = np.array(goal_img, dtype=np.uint8)
        else:
            self._goal_rgb = np.asarray(goal_img, dtype=np.uint8)

    # ── Episode save ──────────────────────────────────────────────────────────

    def save(
        self,
        goal_img:      Optional["PILImage.Image | np.ndarray"] = None,
        goal_position: Optional[np.ndarray] = None,
    ) -> Path:
        """
        Flush all buffers to disk.  Returns path to saved file.

        Format is HDF5 if h5py is available, otherwise .npz bundle.
        """
        if goal_img is not None:
            self.set_goal_image(goal_img)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        ep_id   = f"ep_{self._session_id}_{str(uuid.uuid4())[:8]}"
        T       = len(self._timestamps)

        if T == 0:
            raise RuntimeError("No steps recorded.")

        rgb_arr  = np.stack(self._rgb,      axis=0)  # (T, H, W, 3)
        pos_arr  = np.stack(self._position, axis=0)  # (T, 2)
        yaw_arr  = np.array(self._yaw,  dtype=np.float32)
        ts_arr   = np.array(self._timestamps, dtype=np.int64)
        lv_arr   = np.stack(self._lin_vel,  axis=0)
        av_arr   = np.stack(self._ang_vel,  axis=0)
        un_arr   = np.stack(self._u_nom,    axis=0)
        us_arr   = np.stack(self._u_safe,   axis=0)
        cv_arr   = np.stack(self._cmd_vel,  axis=0)
        md_arr   = np.array(self._min_dist, dtype=np.float32)
        ca_arr   = np.array(self._cbf_active, dtype=bool)
        es_arr   = np.array(self._estop,    dtype=bool)
        hm_arr   = np.array(self._h_min,    dtype=np.float32)

        # Depth: stack if all non-None, else NaN array
        if any(d is not None for d in self._depth):
            depth_arr = np.stack(
                [d if d is not None else np.full((self._H, self._W), np.nan, np.float32)
                 for d in self._depth],
                axis=0,
            )
        else:
            depth_arr = np.full((T, self._H, self._W), np.nan, dtype=np.float32)

        goal_rgb = getattr(self, "_goal_rgb", None)

        if _H5_OK:
            path = self._save_hdf5(
                ep_id, T, ts_arr, rgb_arr, depth_arr,
                pos_arr, yaw_arr, lv_arr, av_arr,
                cv_arr, un_arr, us_arr,
                md_arr, ca_arr, es_arr, hm_arr,
                goal_rgb, goal_position,
            )
        else:
            path = self._save_npz(
                ep_id, ts_arr, rgb_arr, pos_arr, yaw_arr,
                un_arr, us_arr, cv_arr, md_arr, ca_arr, goal_rgb,
            )

        return path

    def _save_hdf5(
        self, ep_id, T, ts, rgb, depth,
        pos, yaw, lv, av, cv, un, us, md, ca, es, hm,
        goal_rgb, goal_pos,
    ) -> Path:
        import h5py
        path = self._output_dir / f"{ep_id}.h5"
        with h5py.File(path, "w") as f:
            # /meta
            m = f.create_group("meta")
            m.attrs["robot_name"]       = "yahboom_m3pro"
            m.attrs["platform"]         = self._platform
            m.attrs["environment"]      = self._env_name
            m.attrs["camera_frame"]     = self._camera_frame
            m.attrs["session_id"]       = self._session_id
            m.attrs["fleetsafe"]        = self._fleetsafe
            m.attrs["model_name"]       = self._model_name
            m.attrs["T"]                = T
            m.attrs["image_H"]          = self._H
            m.attrs["image_W"]          = self._W
            m.attrs["schema_version"]   = "1.0"

            # /time
            t = f.create_group("time")
            t.create_dataset("timestamps_ns", data=ts, compression="gzip")

            # /obs
            o = f.create_group("obs")
            o.create_dataset("rgb",   data=rgb,   dtype=np.uint8,    compression="gzip", compression_opts=4)
            o.create_dataset("depth", data=depth, dtype=np.float32,  compression="gzip", compression_opts=4)

            # /state
            s = f.create_group("state")
            s.create_dataset("position",         data=pos, dtype=np.float32)
            s.create_dataset("yaw",              data=yaw, dtype=np.float32)
            s.create_dataset("linear_velocity",  data=lv,  dtype=np.float32)
            s.create_dataset("angular_velocity", data=av,  dtype=np.float32)

            # /actions
            a = f.create_group("actions")
            a.create_dataset("cmd_vel", data=cv, dtype=np.float32)
            a.create_dataset("u_nom",   data=un, dtype=np.float32)
            a.create_dataset("u_safe",  data=us, dtype=np.float32)

            # /safety
            sf = f.create_group("safety")
            sf.create_dataset("min_dist_m",      data=md, dtype=np.float32)
            sf.create_dataset("cbf_active",      data=ca, dtype=bool)
            sf.create_dataset("estop_triggered", data=es, dtype=bool)
            sf.create_dataset("h_min",           data=hm, dtype=np.float32)

            # /goals
            if goal_rgb is not None or goal_pos is not None:
                g = f.create_group("goals")
                if goal_rgb is not None:
                    g.create_dataset("goal_rgb", data=goal_rgb, dtype=np.uint8, compression="gzip")
                if goal_pos is not None:
                    g.create_dataset("goal_position",
                                     data=np.asarray(goal_pos, np.float32).ravel()[:2])

        return path

    def _save_npz(
        self, ep_id, ts, rgb, pos, yaw, un, us, cv, md, ca, goal_rgb
    ) -> Path:
        """Fallback: save as .npz when h5py is not installed."""
        path = self._output_dir / f"{ep_id}.npz"
        arrays: dict = {
            "timestamps_ns": ts,
            "rgb":           rgb,
            "position":      pos,
            "yaw":           yaw,
            "u_nom":         un,
            "u_safe":        us,
            "cmd_vel":       cv,
            "min_dist_m":    md,
            "cbf_active":    ca,
        }
        if goal_rgb is not None:
            arrays["goal_rgb"] = goal_rgb
        np.savez_compressed(path, **arrays)
        return path

    def close(
        self,
        goal_img:      Optional["PILImage.Image | np.ndarray"] = None,
        goal_position: Optional[np.ndarray] = None,
    ) -> Path:
        """Alias for save() — matches the context-manager mental model."""
        return self.save(goal_img=goal_img, goal_position=goal_position)

    @property
    def n_steps(self) -> int:
        return len(self._timestamps)


# ── HDF5 → GNM converter ──────────────────────────────────────────────────────

def hdf5_to_gnm(
    h5_path:      str | Path,
    output_dir:   str | Path,
    traj_name:    Optional[str] = None,
) -> Path:
    """
    Convert one HDF5 episode file to the official GNM trajectory format.

    Output:
        output_dir/<traj_name>/
            0.jpg  1.jpg  ...  N.jpg    (85×64 RGB)
            traj_data.pkl               {"position": (T,2), "yaw": (T,)}

    Only /obs/rgb and /state/position,yaw are used — matching the baseline.
    """
    import pickle

    if not _H5_OK:
        raise ImportError("h5py is required for HDF5 reading: pip install h5py")
    if not _PIL_OK:
        raise ImportError("Pillow is required: pip install Pillow")

    import h5py
    h5_path  = Path(h5_path)
    out_root = Path(output_dir)

    if traj_name is None:
        traj_name = h5_path.stem

    traj_dir = out_root / traj_name
    traj_dir.mkdir(parents=True, exist_ok=True)

    with h5py.File(h5_path, "r") as f:
        rgb_arr = f["/obs/rgb"][:]             # (T, H, W, 3) uint8
        pos_arr = f["/state/position"][:]      # (T, 2)
        yaw_arr = f["/state/yaw"][:]           # (T,)

    T = len(rgb_arr)

    for i in range(T):
        PILImage.fromarray(rgb_arr[i]).save(traj_dir / f"{i}.jpg")

    traj_data = {
        "position": pos_arr.astype(np.float32),
        "yaw":      yaw_arr.astype(np.float32),
    }
    with open(traj_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(traj_data, f)

    return traj_dir


def batch_hdf5_to_gnm(
    h5_dir:       str | Path,
    output_dir:   str | Path,
    eval_fraction: float = 0.1,
    seed:         int   = 42,
) -> dict:
    """
    Convert all .h5 files in h5_dir to GNM format with train/test split.

    Returns summary dict with n_train, n_test, traj_names.
    """
    import random as _random
    import pickle

    h5_dir     = Path(h5_dir)
    output_dir = Path(output_dir)
    h5_files   = sorted(h5_dir.glob("*.h5"))
    if not h5_files:
        raise ValueError(f"No .h5 files found in {h5_dir}")

    rng = _random.Random(seed)
    files = h5_files[:]
    rng.shuffle(files)
    n_test  = max(1, int(len(files) * eval_fraction))
    splits  = {
        "train": files[:-n_test],
        "test":  files[-n_test:],
    }

    dataset_name = h5_dir.name
    summaries    = {"train": [], "test": []}

    for split_name, split_files in splits.items():
        for h5f in split_files:
            traj_name = h5f.stem
            traj_dir  = hdf5_to_gnm(h5f, output_dir / split_name, traj_name)
            summaries[split_name].append(traj_name)

        # Write traj_names.txt
        split_txt_dir = output_dir / "data_splits" / dataset_name / split_name
        split_txt_dir.mkdir(parents=True, exist_ok=True)
        with open(split_txt_dir / "traj_names.txt", "w") as f:
            f.write("\n".join(summaries[split_name]) + "\n")

    # Write data_config.yaml
    try:
        import yaml
        data_config = {
            "dataset_name":            dataset_name,
            "data_folder":             str(output_dir.resolve()),
            "train":                   f"data_splits/{dataset_name}/train",
            "test":                    f"data_splits/{dataset_name}/test",
            "end_slack":               3,
            "goals_per_obs":           1,
            "negative_mining":         True,
            "metric_waypoint_spacing": 0.25,
        }
        with open(output_dir / "data_config.yaml", "w") as f:
            yaml.safe_dump(data_config, f)
    except ImportError:
        pass

    return {
        "dataset_name": dataset_name,
        "n_train":  len(summaries["train"]),
        "n_test":   len(summaries["test"]),
        "train":    summaries["train"],
        "test":     summaries["test"],
    }
