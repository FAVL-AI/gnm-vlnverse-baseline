# %% [markdown]
# # FleetSafe-GNM / Yahboom / VLNVerse — EDA, Training, Profiling, and Safety Notebook
#
# This notebook is my complete, explainable notebook for the GNM navigation model, the stopping model, and the FleetSafe safety layer.
#
# It is written for a normal audience. I explain the robotics words before using them, then I show the data checks, plots, training steps, and safety checks.
#
# The aim is not just to train a model. The aim is to show a clear evidence trail:
#
# 1. what data I have;
# 2. what is inside each trajectory;
# 3. whether the data has missing values, duplicates, outliers, or broken records;
# 4. how the robot moves through the scenes;
# 5. how stopping methods are trained and compared;
# 6. how the safety layer checks movement before the robot receives the command;
# 7. what can be claimed now and what still needs live Yahboom evidence.
#
# This notebook can run in local Jupyter, VS Code notebooks, Kaggle, or Google Colab. If the real dataset is not present, it creates clearly marked synthetic demo data so every section can still run.
# %% [markdown]
# # 0. Key words explained first
#
# ## GNM
#
# GNM means **General Navigation Model**. In simple words, it is the robot's navigation brain. It looks at visual information and predicts where the robot should move next.
#
# ## VLN
#
# VLN means **Vision-Language Navigation**. It combines:
#
# - **vision**, meaning images from a camera;
# - **language**, meaning instructions or goals;
# - **navigation**, meaning moving through an environment to reach a target.
#
# ## FleetSafe
#
# FleetSafe is the safety layer. It sits after the navigation model and before the movement command reaches the robot. If the model suggests a dangerous movement, FleetSafe can slow it, change it, or stop it.
#
# ## ROS 2
#
# ROS 2 means **Robot Operating System 2**. It is a communication system for robots. It lets the camera, LiDAR, odometry, controller, model, and safety layer send messages to each other.
#
# ## ROS topic
#
# A ROS topic is like a named message channel. Important topics in this project are:
#
# - `/camera/image_raw`: the camera image the model sees;
# - `/odom`: odometry, meaning the robot's estimate of where it is and how it is moving;
# - `/tf`: the transform tree, meaning how robot parts are positioned compared with each other;
# - `/scan`: LiDAR obstacle readings;
# - `/cmd_vel`: command velocity, meaning the movement command sent to the robot.
#
# ## ROS 2 Bridge
#
# The ROS 2 Bridge connects Isaac Sim to ROS 2. A robot can be visible in Isaac but still publish no ROS topics. The bridge and OmniGraph nodes are what make Isaac data appear in ROS 2.
#
# ## rosbag2
#
# rosbag2 is the ROS 2 recording tool. It records robot topics into a folder so they can be replayed, inspected, or converted into a training dataset.
#
# ## Episode
#
# An episode is one recorded robot run. For example, `episode_001` means the first recorded run.
#
# ## Trajectory
#
# A trajectory is the robot's path over time. It is like a breadcrumb trail of positions.
#
# ## Waypoint
#
# A waypoint is a short-term target. Instead of planning the whole route in one jump, the model predicts the next small step.
#
# ## SR, OSR, and NE
#
# - **SR** means Success Rate. It measures whether the robot finished correctly.
# - **OSR** means Oracle Success Rate. It measures whether the robot ever entered the goal area, even if it failed to stop there.
# - **NE** means Navigation Error. It measures final distance from the goal. Lower is better.
#
# If OSR is much higher than SR, the robot often reaches the right area but fails to stop correctly.
#
# ## LiDAR
#
# LiDAR means Light Detection and Ranging. It measures obstacle distances around the robot.
#
# ## OmniGraph
#
# OmniGraph is Isaac Sim's graph system. It connects simulation objects to actions and ROS 2 publishers.
#
# ## USD and USDA
#
# USD means Universal Scene Description. It is a 3D scene format used by Isaac Sim. USDA is the text version of USD.
#
# ## Working tree
#
# The Git working tree is the current state of files in the repository. `git status --short` shows whether files are changed, new, or clean.
# %%
# 1. Optional package setup
# Run this cell in Colab/Kaggle/local notebooks. It installs missing packages only when needed.

import sys, subprocess, importlib.util

packages = [
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("matplotlib", "matplotlib"),
    ("sklearn", "scikit-learn"),
    ("torch", "torch"),
    ("PIL", "Pillow"),
]

for import_name, pip_name in packages:
    if importlib.util.find_spec(import_name) is None:
        print(f"[INSTALL] {pip_name}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pip_name])
    else:
        print(f"[OK] {import_name}")

# %%
# 2. Imports and reproducibility

from __future__ import annotations

import os, re, gc, json, math, time, pickle, random, warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from PIL import Image

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report,
    roc_auc_score,
    roc_curve,
)

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

warnings.filterwarnings("ignore")

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["axes.grid"] = True

print("[OK] Notebook imports complete")
print("Torch:", torch.__version__)

# %% [markdown]
# # 1. Project paths and run mode
#
# The notebook looks for the repository automatically. If the real dataset is not present, it uses synthetic demo data. Synthetic data is only for testing the notebook flow. It is not research evidence.
# %%
# 3. Project paths

CANDIDATE_REPO_ROOTS = [
    Path.cwd(),
    Path.home() / "robotics" / "gnm-vlnverse-baseline",
    Path("/content/gnm-vlnverse-baseline"),
]

REPO_ROOT = None
for p in CANDIDATE_REPO_ROOTS:
    if (p / "README.md").exists() or (p / "scripts").exists():
        REPO_ROOT = p
        break

if REPO_ROOT is None:
    REPO_ROOT = Path.cwd()

DATA_ROOT = REPO_ROOT / "datasets" / "vlntube"
TRAIN_ROOT = DATA_ROOT / "train"
VAL_ROOT = DATA_ROOT / "val"
OUTPUT_ROOT = REPO_ROOT / "results" / "notebook_outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

print("REPO_ROOT:", REPO_ROOT)
print("DATA_ROOT:", DATA_ROOT)
print("TRAIN_ROOT exists:", TRAIN_ROOT.exists())
print("VAL_ROOT exists:", VAL_ROOT.exists())
print("OUTPUT_ROOT:", OUTPUT_ROOT)

# %% [markdown]
# # 2. Full data flow diagram
#
# This diagram shows how the work should flow from robot/simulator data into training and safety checks.
# %%
def draw_data_flow():
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.axis("off")
    boxes = [
        ("Isaac Sim / Yahboom\ncamera, lidar, odometry", 0.05, 0.66),
        ("ROS 2 topics\n/camera /odom /tf /scan /cmd_vel", 0.31, 0.66),
        ("rosbag2 episode\nrecorded robot run", 0.57, 0.66),
        ("GNM dataset\nconverted training format", 0.83, 0.66),
        ("EDA + profiling\nnulls, outliers, plots", 0.20, 0.31),
        ("GNM navigation\nwaypoints + movement", 0.45, 0.31),
        ("Stop model\nlogistic + temporal", 0.70, 0.31),
        ("FleetSafe\nsafe command filter", 0.45, 0.06),
    ]
    for text, x, y in boxes:
        ax.text(x, y, text, ha="center", va="center", fontsize=10,
                bbox=dict(boxstyle="round,pad=0.5", linewidth=1.5))
    arrows = [
        ((0.17,0.66),(0.25,0.66)), ((0.43,0.66),(0.51,0.66)), ((0.69,0.66),(0.77,0.66)),
        ((0.57,0.59),(0.25,0.39)), ((0.83,0.59),(0.45,0.39)), ((0.83,0.59),(0.70,0.39)),
        ((0.45,0.23),(0.45,0.13)), ((0.70,0.23),(0.45,0.13)),
    ]
    for a, b in arrows:
        ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="->", lw=2))
    ax.set_title("FleetSafe-GNM data and training flow", fontsize=16, pad=18)
    plt.show()

draw_data_flow()

# %% [markdown]
# # 3. Load and inspect trajectory files
#
# A `traj_data.pkl` file stores movement information for one robot run. The loader below tries to extract positions, yaw, path length, start position, and end position.
# %%
def find_trajectory_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("*/traj_data.pkl"))

def infer_scene_id(path: Path) -> str:
    m = re.search(r"(kujiale_\d+)", str(path))
    return m.group(1) if m else "unknown_scene"

def safe_load_pickle(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)

def extract_position_array(obj: Any) -> Optional[np.ndarray]:
    if isinstance(obj, dict):
        for key in ["position", "positions", "pos", "poses", "trajectory", "path"]:
            if key in obj:
                arr = np.asarray(obj[key])
                if arr.ndim >= 2 and arr.shape[0] > 1:
                    return arr.reshape(arr.shape[0], -1)
        for v in obj.values():
            if isinstance(v, (dict, list, tuple, np.ndarray)):
                arr = extract_position_array(v)
                if arr is not None:
                    return arr
    elif isinstance(obj, (list, tuple, np.ndarray)):
        arr = np.asarray(obj)
        if arr.ndim >= 2 and arr.shape[0] > 1 and np.issubdtype(arr.dtype, np.number):
            return arr.reshape(arr.shape[0], -1)
    return None

def extract_yaw_array(obj: Any, length: int) -> np.ndarray:
    if isinstance(obj, dict):
        for key in ["yaw", "yaws", "heading", "theta"]:
            if key in obj:
                arr = np.asarray(obj[key]).reshape(-1)
                if len(arr) == length:
                    return arr.astype(float)
    return np.zeros(length, dtype=float)

def summarize_trajectory(path: Path, split: str) -> Dict[str, Any]:
    row = dict(split=split, path=str(path), episode_dir=path.parent.name, scene_id=infer_scene_id(path),
               load_ok=False, n_frames=0, has_position=False, has_yaw=False,
               path_length=np.nan, displacement=np.nan, start_x=np.nan, start_y=np.nan, end_x=np.nan, end_y=np.nan)
    try:
        obj = safe_load_pickle(path)
        pos = extract_position_array(obj)
        if pos is None:
            return row
        pos = pos.astype(float)
        n = pos.shape[0]
        xy = pos[:, :2]
        step_dist = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        row.update(load_ok=True, n_frames=n, has_position=True,
                   has_yaw=len(extract_yaw_array(obj, n)) == n,
                   path_length=float(step_dist.sum()), displacement=float(np.linalg.norm(xy[-1] - xy[0])),
                   start_x=float(xy[0,0]), start_y=float(xy[0,1]), end_x=float(xy[-1,0]), end_y=float(xy[-1,1]))
    except Exception as exc:
        row["error"] = repr(exc)
    return row

train_files = find_trajectory_files(TRAIN_ROOT)
val_files = find_trajectory_files(VAL_ROOT)
rows = [summarize_trajectory(p, "train") for p in train_files] + [summarize_trajectory(p, "val") for p in val_files]
traj_df = pd.DataFrame(rows)
print("train files:", len(train_files), "val files:", len(val_files))
traj_df.head()

# %%
# Synthetic fallback so the notebook still runs without private/local dataset files.

def synthetic_traj_df(n_train=80, n_val=20):
    rng = np.random.default_rng(SEED)
    scenes = ["kujiale_0092", "kujiale_0118", "kujiale_0203", "kujiale_0271"]
    rows = []
    for split, n in [("train", n_train), ("val", n_val)]:
        for i in range(n):
            scene = rng.choice(scenes)
            frames = int(rng.integers(30, 140))
            xy = np.cumsum(rng.normal(0.05, 0.03, size=(frames, 2)), axis=0)
            step_dist = np.linalg.norm(np.diff(xy, axis=0), axis=1)
            rows.append(dict(split=split, path=f"synthetic/{split}/{scene}_{i}/traj_data.pkl", episode_dir=f"{scene}_synthetic_{i}",
                             scene_id=scene, load_ok=True, n_frames=frames, has_position=True, has_yaw=True,
                             path_length=float(step_dist.sum()), displacement=float(np.linalg.norm(xy[-1]-xy[0])),
                             start_x=float(xy[0,0]), start_y=float(xy[0,1]), end_x=float(xy[-1,0]), end_y=float(xy[-1,1]), synthetic=True))
    return pd.DataFrame(rows)

if traj_df.empty or traj_df["load_ok"].sum() == 0:
    print("[WARN] No real trajectory files loaded. Using synthetic demo data.")
    traj_df = synthetic_traj_df()
else:
    traj_df["synthetic"] = False
    print("[OK] Real trajectory summaries loaded.")

display(traj_df.head())
print("Rows:", len(traj_df))

# %% [markdown]
# # 4. Data audit: missing values, duplicates, and basic quality
#
# Before training, I check for missing values, duplicates, wrong split names, and invalid lengths. This protects the training pipeline from bad data.
# %%
print("Split counts")
display(traj_df["split"].value_counts().to_frame("count"))

print("Scene counts")
display(traj_df.groupby(["split", "scene_id"]).size().to_frame("count"))

print("Null counts")
display(traj_df.isna().sum().sort_values(ascending=False).to_frame("null_count"))

checks = {
    "all_loaded": bool(traj_df["load_ok"].all()),
    "positive_frame_counts": bool((traj_df["n_frames"] > 0).all()),
    "valid_splits": bool(traj_df["split"].isin(["train", "val"]).all()),
    "duplicate_episode_dirs": int(traj_df["episode_dir"].duplicated().sum()),
}
print(json.dumps(checks, indent=2))

display(traj_df.describe(include="all").T)

# %% [markdown]
# # 5. Scene distribution and trajectory length plots
#
# These plots show how much data each scene has and whether episode lengths look reasonable.
# %%
def save_fig(name: str):
    path = OUTPUT_ROOT / name
    plt.tight_layout()
    plt.savefig(path, dpi=160, bbox_inches="tight")
    print("[SAVED]", path)

pivot = traj_df.groupby(["scene_id", "split"]).size().unstack(fill_value=0)
ax = pivot.plot(kind="bar", figsize=(11, 6))
ax.set_title("Trajectory count per scene")
ax.set_xlabel("Scene")
ax.set_ylabel("Trajectory count")
plt.xticks(rotation=45, ha="right")
save_fig("scene_distribution.png")
plt.show()

display(pivot)

fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(traj_df["n_frames"], bins=30)
ax.set_title("Trajectory frame count distribution")
ax.set_xlabel("Frames per episode")
ax.set_ylabel("Episode count")
save_fig("trajectory_frame_count_distribution.png")
plt.show()

fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(traj_df["path_length"], bins=30)
ax.set_title("Trajectory path length distribution")
ax.set_xlabel("Path length")
ax.set_ylabel("Episode count")
save_fig("trajectory_path_length_distribution.png")
plt.show()

# %% [markdown]
# # 6. Outlier detection
#
# Outliers are unusual examples. They are not automatically wrong, but I need to know they exist.
# %%
num_cols = ["n_frames", "path_length", "displacement", "start_x", "start_y", "end_x", "end_y"]
profile = traj_df.copy()
for col in num_cols:
    q1, q3 = profile[col].quantile([0.25, 0.75])
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    profile[f"{col}_outlier"] = (profile[col] < lower) | (profile[col] > upper)

outlier_cols = [c for c in profile.columns if c.endswith("_outlier")]
display(profile[outlier_cols].sum().sort_values(ascending=False).to_frame("outlier_count"))
display(profile.loc[profile[outlier_cols].any(axis=1), ["split", "scene_id", "episode_dir", "n_frames", "path_length", "displacement"] + outlier_cols].head(30))

# %% [markdown]
# # 7. Correlation heatmap
#
# Correlation tells me whether two numeric features move together. This is useful for spotting features that may carry similar information.
# %%
corr = traj_df[num_cols].corr(numeric_only=True)
fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(corr.values, aspect="auto")
ax.set_xticks(range(len(corr.columns)))
ax.set_yticks(range(len(corr.index)))
ax.set_xticklabels(corr.columns, rotation=45, ha="right")
ax.set_yticklabels(corr.index)
ax.set_title("Trajectory feature correlation heatmap")
fig.colorbar(im, ax=ax)
for i in range(len(corr.index)):
    for j in range(len(corr.columns)):
        ax.text(j, i, f"{corr.values[i,j]:.2f}", ha="center", va="center", fontsize=8)
save_fig("trajectory_correlation_heatmap.png")
plt.show()
display(corr)

# %% [markdown]
# # 8. Movement map
#
# This plot shows where episodes start and end. It helps reveal whether the data covers many areas or is clustered.
# %%
fig, ax = plt.subplots(figsize=(9, 8))
for split, g in traj_df.groupby("split"):
    ax.scatter(g["start_x"], g["start_y"], marker="o", alpha=0.7, label=f"{split} start")
    ax.scatter(g["end_x"], g["end_y"], marker="x", alpha=0.7, label=f"{split} end")
ax.set_title("Episode start and end positions")
ax.set_xlabel("x position")
ax.set_ylabel("y position")
ax.legend()
ax.axis("equal")
save_fig("episode_start_end_map.png")
plt.show()

# %% [markdown]
# # 9. Build step-level data for stopping models
#
# Stopping happens at a moment inside an episode, so I need step-level rows. Each row is one time step.
#
# If real step positions are available, I extract them. Otherwise, I generate synthetic step rows for demonstration.
# %%
def extract_steps(path: Path, split: str) -> pd.DataFrame:
    obj = safe_load_pickle(path)
    pos = extract_position_array(obj)
    if pos is None:
        return pd.DataFrame()
    pos = pos.astype(float)
    xy = pos[:, :2]
    n = len(xy)
    yaw = extract_yaw_array(obj, n)
    deltas = np.vstack([np.zeros((1,2)), np.diff(xy, axis=0)])
    speed = np.linalg.norm(deltas, axis=1)
    goal = xy[-1]
    dist = np.linalg.norm(goal[None, :] - xy, axis=1)
    rows=[]
    for t in range(n):
        rows.append(dict(split=split, path=str(path), episode_dir=path.parent.name, scene_id=infer_scene_id(path), t=t, n_frames=n,
                         x=float(xy[t,0]), y=float(xy[t,1]), yaw=float(yaw[t]), step_dx=float(deltas[t,0]), step_dy=float(deltas[t,1]),
                         speed_proxy=float(speed[t]), goal_x=float(goal[0]), goal_y=float(goal[1]), dist_to_goal=float(dist[t]),
                         stop_label=int(t >= max(0, n-3))))
    return pd.DataFrame(rows)

frames=[]
if not bool(traj_df["synthetic"].any()):
    for p in train_files: 
        try: frames.append(extract_steps(p, "train"))
        except Exception: pass
    for p in val_files:
        try: frames.append(extract_steps(p, "val"))
        except Exception: pass

if frames:
    step_df = pd.concat(frames, ignore_index=True)
    step_df["synthetic"] = False
else:
    print("[WARN] Using synthetic step data.")
    rng = np.random.default_rng(SEED)
    rows=[]
    for _, ep in traj_df.iterrows():
        n=int(ep.n_frames)
        xy=np.cumsum(rng.normal(0.05,0.03,size=(n,2)),axis=0)
        goal=xy[-1]
        delta=np.vstack([np.zeros((1,2)),np.diff(xy,axis=0)])
        speed=np.linalg.norm(delta,axis=1)
        dist=np.linalg.norm(goal[None,:]-xy,axis=1)
        for t in range(n):
            rows.append(dict(split=ep.split,path=ep.path,episode_dir=ep.episode_dir,scene_id=ep.scene_id,t=t,n_frames=n,
                             x=float(xy[t,0]),y=float(xy[t,1]),yaw=float(rng.normal()),step_dx=float(delta[t,0]),step_dy=float(delta[t,1]),
                             speed_proxy=float(speed[t]),goal_x=float(goal[0]),goal_y=float(goal[1]),dist_to_goal=float(dist[t]),
                             stop_label=int(t>=max(0,n-3)),synthetic=True))
    step_df=pd.DataFrame(rows)

print("Step rows:", len(step_df))
display(step_df.head())

# %% [markdown]
# # 10. Feature engineering
#
# I create the features used by the stopping models:
#
# - distance to goal;
# - waypoint size;
# - speed proxy;
# - rolling averages;
# - trends.
#
# A rolling average looks at the recent past. A trend tells whether something is increasing or decreasing.
# %%
step_df = step_df.sort_values(["episode_dir", "t"]).reset_index(drop=True)
step_df["waypoint_norm"] = np.sqrt(step_df["step_dx"]**2 + step_df["step_dy"]**2)
group = step_df.groupby("episode_dir", group_keys=False)
step_df["rolling_dist_mean_5"] = group["dist_to_goal"].apply(lambda s: s.rolling(5, min_periods=1).mean())
step_df["rolling_waypoint_mean_5"] = group["waypoint_norm"].apply(lambda s: s.rolling(5, min_periods=1).mean())
step_df["rolling_speed_mean_5"] = group["speed_proxy"].apply(lambda s: s.rolling(5, min_periods=1).mean())
step_df["dist_trend"] = group["dist_to_goal"].diff().fillna(0.0)
step_df["waypoint_trend"] = group["waypoint_norm"].diff().fillna(0.0)
step_df["speed_trend"] = group["speed_proxy"].diff().fillna(0.0)

feature_cols = [
    "dist_to_goal", "waypoint_norm", "speed_proxy",
    "rolling_dist_mean_5", "rolling_waypoint_mean_5", "rolling_speed_mean_5",
    "dist_trend", "waypoint_trend", "speed_trend",
]

display(step_df[feature_cols + ["stop_label"]].head())

# %% [markdown]
# # 11. Feature plots and stop-label balance
#
# A stop model needs examples of both moving and stopping. If stop examples are too rare, the model can learn to always say move.
# %%
label_counts = step_df["stop_label"].value_counts().sort_index()
display(label_counts.to_frame("count"))
fig, ax = plt.subplots(figsize=(6,4))
ax.bar(["move", "stop"], [label_counts.get(0,0), label_counts.get(1,0)])
ax.set_title("Stop label balance")
ax.set_ylabel("Step count")
save_fig("stop_label_balance.png")
plt.show()

for col in ["dist_to_goal", "waypoint_norm", "speed_proxy"]:
    fig, ax = plt.subplots(figsize=(8,4))
    ax.hist(step_df[col].dropna(), bins=40)
    ax.set_title(f"Distribution of {col}")
    ax.set_xlabel(col)
    ax.set_ylabel("Step count")
    save_fig(f"distribution_{col}.png")
    plt.show()

# %%
step_corr = step_df[feature_cols + ["stop_label"]].corr(numeric_only=True)
fig, ax = plt.subplots(figsize=(10, 8))
im = ax.imshow(step_corr.values, aspect="auto")
ax.set_xticks(range(len(step_corr.columns)))
ax.set_yticks(range(len(step_corr.index)))
ax.set_xticklabels(step_corr.columns, rotation=45, ha="right")
ax.set_yticklabels(step_corr.index)
ax.set_title("Step-level feature correlation heatmap")
fig.colorbar(im, ax=ax)
for i in range(len(step_corr.index)):
    for j in range(len(step_corr.columns)):
        ax.text(j, i, f"{step_corr.values[i,j]:.2f}", ha="center", va="center", fontsize=7)
save_fig("step_feature_correlation_heatmap.png")
plt.show()

# %% [markdown]
# # 12. Hand-tuned waypoint gate
#
# This is a simple human-made rule:
#
# > If the waypoint is very small, predict stop.
#
# It is easy to explain, but it may be too simple for real robot stopping.
# %%
def evaluate_binary(y_true, y_pred, name):
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return dict(method=name, accuracy=accuracy_score(y_true, y_pred), precision=precision, recall=recall, f1=f1)

train_step_df = step_df[step_df.split == "train"].copy()
val_step_df = step_df[step_df.split == "val"].copy()

threshold = train_step_df["waypoint_norm"].quantile(0.10)
val_pred_gate = (val_step_df["waypoint_norm"] <= threshold).astype(int)
gate_result = evaluate_binary(val_step_df["stop_label"], val_pred_gate, "Hand-tuned waypoint gate")
print("Waypoint threshold:", threshold)
display(pd.DataFrame([gate_result]))

cm = confusion_matrix(val_step_df["stop_label"], val_pred_gate)
fig, ax = plt.subplots(figsize=(5,5))
ax.imshow(cm)
ax.set_title("Confusion matrix — hand-tuned waypoint gate")
ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(["move","stop"]); ax.set_yticklabels(["move","stop"])
ax.set_xlabel("Predicted"); ax.set_ylabel("True")
for i in range(2):
    for j in range(2): ax.text(j,i,str(cm[i,j]),ha="center",va="center")
save_fig("confusion_matrix_hand_tuned_waypoint_gate.png")
plt.show()

# %% [markdown]
# # 13. Logistic stop head
#
# A logistic stop head is a simple learned classifier. It learns from features and predicts stop probability.
#
# It is stronger than a hand rule, but it still only sees a feature row, not the full recent history.
# %%
X_train = train_step_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0).values
y_train = train_step_df["stop_label"].values
X_val = val_step_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0).values
y_val = val_step_df["stop_label"].values

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s = scaler.transform(X_val)

logistic = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED)
logistic.fit(X_train_s, y_train)
prob_logistic = logistic.predict_proba(X_val_s)[:, 1]
pred_logistic = (prob_logistic >= 0.5).astype(int)
logistic_result = evaluate_binary(y_val, pred_logistic, "Logistic stop head")
try: logistic_result["roc_auc"] = roc_auc_score(y_val, prob_logistic)
except Exception: logistic_result["roc_auc"] = np.nan

display(pd.DataFrame([logistic_result]))
print(classification_report(y_val, pred_logistic, target_names=["move", "stop"], zero_division=0))

# %%
cm = confusion_matrix(y_val, pred_logistic)
fig, ax = plt.subplots(figsize=(5,5))
ax.imshow(cm)
ax.set_title("Confusion matrix — logistic stop head")
ax.set_xticks([0,1]); ax.set_yticks([0,1])
ax.set_xticklabels(["move","stop"]); ax.set_yticklabels(["move","stop"])
ax.set_xlabel("Predicted"); ax.set_ylabel("True")
for i in range(2):
    for j in range(2): ax.text(j,i,str(cm[i,j]),ha="center",va="center")
save_fig("confusion_matrix_logistic_stop_head.png")
plt.show()

try:
    fpr, tpr, _ = roc_curve(y_val, prob_logistic)
    fig, ax = plt.subplots(figsize=(7,5))
    ax.plot(fpr, tpr, label="Logistic stop head")
    ax.plot([0,1], [0,1], linestyle="--", label="Random")
    ax.set_title("ROC curve — logistic stop head")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.legend()
    save_fig("roc_curve_logistic_stop_head.png")
    plt.show()
except Exception as exc:
    print("[SKIP] ROC curve:", exc)

# %% [markdown]
# # 14. Temporal neural stop head
#
# The temporal neural stop head uses history. It sees a window of recent steps, not only one row.
#
# This matters because stopping is usually a pattern over time. The robot may be approaching, slowing down, drifting, or oscillating. A temporal model can learn those patterns better than a single-step model.
# %%
class TemporalStopDataset(Dataset):
    def __init__(self, df, feature_cols, window=8):
        self.X=[]; self.y=[]; self.window=window
        for _, ep in df.groupby("episode_dir"):
            ep=ep.sort_values("t")
            feats=ep[feature_cols].replace([np.inf,-np.inf],np.nan).fillna(0).values.astype(np.float32)
            labels=ep["stop_label"].values.astype(np.float32)
            for i in range(len(ep)):
                start=max(0, i-window+1)
                seq=feats[start:i+1]
                if len(seq)<window:
                    pad=np.repeat(seq[:1], window-len(seq), axis=0)
                    seq=np.vstack([pad,seq])
                self.X.append(seq); self.y.append(labels[i])
        self.X=np.stack(self.X); self.y=np.asarray(self.y).reshape(-1,1)
    def __len__(self): return len(self.y)
    def __getitem__(self, idx): return torch.tensor(self.X[idx]), torch.tensor(self.y[idx])

class TemporalStopHead(nn.Module):
    def __init__(self, n_features, hidden=48):
        super().__init__()
        self.gru=nn.GRU(n_features, hidden, batch_first=True)
        self.head=nn.Sequential(nn.Linear(hidden,32), nn.ReLU(), nn.Dropout(0.10), nn.Linear(32,1))
    def forward(self,x):
        _,h=self.gru(x)
        return self.head(h[-1])

window=8
train_ds=TemporalStopDataset(train_step_df, feature_cols, window)
val_ds=TemporalStopDataset(val_step_df, feature_cols, window)
train_loader=DataLoader(train_ds, batch_size=256, shuffle=True)
val_loader=DataLoader(val_ds, batch_size=512, shuffle=False)

device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
model=TemporalStopHead(len(feature_cols)).to(device)
pos_weight=torch.tensor([(len(y_train)-y_train.sum())/max(y_train.sum(),1)], dtype=torch.float32).to(device)
criterion=nn.BCEWithLogitsLoss(pos_weight=pos_weight)
optimizer=torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
print("Device:", device, "Train sequences:", len(train_ds), "Val sequences:", len(val_ds))

# %%
def run_epoch(train=True):
    model.train(train)
    total=0; probs=[]; labels=[]
    loader=train_loader if train else val_loader
    for xb,yb in loader:
        xb=xb.to(device); yb=yb.to(device)
        if train: optimizer.zero_grad()
        logits=model(xb)
        loss=criterion(logits,yb)
        if train:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),2.0)
            optimizer.step()
        total+=loss.item()*len(xb)
        probs.extend(torch.sigmoid(logits).detach().cpu().numpy().reshape(-1).tolist())
        labels.extend(yb.detach().cpu().numpy().reshape(-1).tolist())
    labels=np.asarray(labels).astype(int); preds=(np.asarray(probs)>=0.5).astype(int)
    p,r,f1,_=precision_recall_fscore_support(labels,preds,average="binary",zero_division=0)
    return total/max(len(loader.dataset),1), accuracy_score(labels,preds), f1

history=[]
for epoch in range(1,9):
    tr=run_epoch(True); va=run_epoch(False)
    row=dict(epoch=epoch, train_loss=tr[0], train_acc=tr[1], train_f1=tr[2], val_loss=va[0], val_acc=va[1], val_f1=va[2])
    history.append(row); print(row)
history_df=pd.DataFrame(history)
display(history_df)

# %%
fig, ax = plt.subplots(figsize=(8,5))
ax.plot(history_df.epoch, history_df.train_loss, marker="o", label="Train loss")
ax.plot(history_df.epoch, history_df.val_loss, marker="o", label="Validation loss")
ax.set_title("Temporal stop head loss")
ax.set_xlabel("Epoch"); ax.set_ylabel("Loss"); ax.legend()
save_fig("temporal_stop_head_loss.png")
plt.show()

fig, ax = plt.subplots(figsize=(8,5))
ax.plot(history_df.epoch, history_df.train_f1, marker="o", label="Train F1")
ax.plot(history_df.epoch, history_df.val_f1, marker="o", label="Validation F1")
ax.set_title("Temporal stop head F1")
ax.set_xlabel("Epoch"); ax.set_ylabel("F1"); ax.legend()
save_fig("temporal_stop_head_f1.png")
plt.show()

# %%
model.eval(); temporal_probs=[]; temporal_labels=[]
with torch.no_grad():
    for xb,yb in val_loader:
        logits=model(xb.to(device))
        temporal_probs.extend(torch.sigmoid(logits).cpu().numpy().reshape(-1).tolist())
        temporal_labels.extend(yb.numpy().reshape(-1).tolist())
temporal_probs=np.asarray(temporal_probs)
temporal_labels=np.asarray(temporal_labels).astype(int)
temporal_preds=(temporal_probs>=0.5).astype(int)
temporal_result=evaluate_binary(temporal_labels, temporal_preds, "Temporal neural stop head")
try: temporal_result["roc_auc"]=roc_auc_score(temporal_labels, temporal_probs)
except Exception: temporal_result["roc_auc"]=np.nan
results_df=pd.DataFrame([gate_result, logistic_result, temporal_result])
display(results_df)

fig, ax=plt.subplots(figsize=(9,5))
ax.bar(results_df.method, results_df.f1)
ax.set_title("Stopping method comparison")
ax.set_ylabel("F1 score")
ax.set_xticklabels(results_df.method, rotation=25, ha="right")
save_fig("stopping_method_comparison.png")
plt.show()

# %% [markdown]
# # 15. Episode metrics: SR, OSR, and NE
#
# This section calculates episode-level success metrics.
#
# - SR checks final success.
# - OSR checks whether the robot ever reached the goal region.
# - NE checks final distance from the goal.
#
# This is how I separate navigation failure from stopping failure.
# %%
def episode_metrics(df, goal_radius=0.50):
    rows=[]
    for ep_name, ep in df.groupby("episode_dir"):
        ep=ep.sort_values("t")
        d=ep["dist_to_goal"].values
        rows.append(dict(episode_dir=ep_name, split=ep.split.iloc[0], scene_id=ep.scene_id.iloc[0],
                         final_ne=float(d[-1]), min_dist=float(np.min(d)), sr=int(d[-1]<=goal_radius), osr=int(np.min(d)<=goal_radius), n_frames=int(ep.n_frames.iloc[0])))
    return pd.DataFrame(rows)

ep_metrics=episode_metrics(step_df)
summary=ep_metrics.groupby("split").agg(SR=("sr","mean"), OSR=("osr","mean"), NE=("final_ne","mean"), episodes=("episode_dir","count")).reset_index()
summary["SR"]*=100; summary["OSR"]*=100
display(summary)

fig, ax=plt.subplots(figsize=(8,5))
x=np.arange(len(summary)); width=0.35
ax.bar(x-width/2, summary.SR, width, label="SR")
ax.bar(x+width/2, summary.OSR, width, label="OSR")
ax.set_xticks(x); ax.set_xticklabels(summary.split)
ax.set_ylabel("Percent"); ax.set_title("SR vs OSR")
ax.legend(); save_fig("sr_vs_osr.png"); plt.show()

# %% [markdown]
# # 16. Image audit
#
# GNM is a visual navigation model, so image quality matters. If images exist, I check image sizes, brightness, and a basic sharpness proxy.
# %%
IMAGE_EXTS={".png",".jpg",".jpeg",".bmp"}
def find_images(root, max_files=1000):
    if not root.exists(): return []
    out=[]
    for p in root.rglob("*"):
        if p.suffix.lower() in IMAGE_EXTS:
            out.append(p)
            if len(out)>=max_files: break
    return out

def image_stats(p):
    try:
        img=Image.open(p).convert("L")
        arr=np.asarray(img).astype(float)
        gx=np.diff(arr,axis=1); gy=np.diff(arr,axis=0)
        return dict(path=str(p), width=img.width, height=img.height, brightness_mean=float(arr.mean()), brightness_std=float(arr.std()), sharpness_proxy=float(np.abs(gx).mean()+np.abs(gy).mean()), ok=True)
    except Exception as exc:
        return dict(path=str(p), ok=False, error=repr(exc))

image_files=find_images(DATA_ROOT)
print("Images found:", len(image_files))
img_df=pd.DataFrame([image_stats(p) for p in image_files[:500]]) if image_files else pd.DataFrame()
display(img_df.head() if not img_df.empty else pd.DataFrame({"message":["No images found in this environment"]}))

if not img_df.empty and img_df.ok.any():
    good=img_df[img_df.ok]
    fig, ax=plt.subplots(figsize=(8,4)); ax.hist(good.brightness_mean,bins=30); ax.set_title("Image brightness distribution"); save_fig("image_brightness_distribution.png"); plt.show()
    fig, ax=plt.subplots(figsize=(8,4)); ax.hist(good.sharpness_proxy,bins=30); ax.set_title("Image sharpness proxy distribution"); save_fig("image_sharpness_distribution.png"); plt.show()
else:
    print("[SKIP] Image plots skipped because images are not available here.")

# %% [markdown]
# # 17. FleetSafe safety layer demonstration
#
# The navigation model proposes movement. FleetSafe checks the movement before it reaches `/cmd_vel`.
#
# In this notebook, I demonstrate the idea with a simple safety filter:
#
# - far obstacle: allow command;
# - close obstacle: slow command;
# - dangerous obstacle: stop command.
#
# This is a practical notebook demonstration, not the final formal safety proof.
# %%
def fleetsafe_filter(proposed_vx, proposed_wz, nearest_obstacle_m, slow_radius=0.80, stop_radius=0.35):
    if nearest_obstacle_m <= stop_radius:
        return 0.0, 0.0, "stop"
    if nearest_obstacle_m <= slow_radius:
        scale=(nearest_obstacle_m-stop_radius)/max(slow_radius-stop_radius,1e-6)
        scale=float(np.clip(scale,0,1))
        return proposed_vx*scale, proposed_wz*scale, "slow"
    return proposed_vx, proposed_wz, "allow"

safety_df=val_step_df.sample(min(2000,len(val_step_df)), random_state=SEED).reset_index(drop=True)
rng=np.random.default_rng(SEED)
safety_df["proposed_vx"]=np.clip(safety_df.speed_proxy*2.0+rng.normal(0,0.03,len(safety_df)),0,0.5)
safety_df["proposed_wz"]=rng.normal(0,0.2,len(safety_df))
safety_df["nearest_obstacle_m"]=np.clip(rng.gamma(2.0,0.45,len(safety_df)),0.05,3.0)
filtered=safety_df.apply(lambda r: fleetsafe_filter(r.proposed_vx,r.proposed_wz,r.nearest_obstacle_m), axis=1)
safety_df["safe_vx"]=[x[0] for x in filtered]
safety_df["safe_wz"]=[x[1] for x in filtered]
safety_df["safety_action"]=[x[2] for x in filtered]
display(safety_df.head())
display(safety_df.safety_action.value_counts().to_frame("count"))

# %%
fig, ax=plt.subplots(figsize=(8,5))
safety_df.safety_action.value_counts().reindex(["allow","slow","stop"]).fillna(0).plot(kind="bar", ax=ax)
ax.set_title("FleetSafe action distribution")
ax.set_xlabel("Safety action"); ax.set_ylabel("Step count")
save_fig("fleetsafe_action_distribution.png"); plt.show()

fig, ax=plt.subplots(figsize=(8,5))
ax.scatter(safety_df.nearest_obstacle_m, safety_df.proposed_vx, alpha=0.3, label="Proposed speed")
ax.scatter(safety_df.nearest_obstacle_m, safety_df.safe_vx, alpha=0.3, label="Safe speed")
ax.set_title("FleetSafe speed filtering")
ax.set_xlabel("Nearest obstacle distance in metres")
ax.set_ylabel("Forward speed")
ax.legend(); save_fig("fleetsafe_speed_filtering.png"); plt.show()

# %% [markdown]
# # 18. Save outputs, model card, and checkpoint
#
# A good notebook should leave behind evidence files. This cell saves:
#
# - a model and dataset card;
# - a temporal stop-head checkpoint;
# - plot files under `results/notebook_outputs`.
# %%
model_card={
    "project":"FleetSafe-GNM Yahboom VLNVerse EDA/training/safety notebook",
    "created_at":time.strftime("%Y-%m-%d %H:%M:%S"),
    "repo_root":str(REPO_ROOT),
    "data_root":str(DATA_ROOT),
    "using_synthetic_data":bool(step_df.synthetic.any()),
    "trajectory_rows":int(len(traj_df)),
    "step_rows":int(len(step_df)),
    "feature_columns":feature_cols,
    "methods_compared":results_df.to_dict(orient="records"),
    "claim_boundary":[
        "Synthetic fallback data is demonstration only.",
        "Valid Yahboom rosbag2 data must pass strict topic and bag validation before real-data training claims.",
        "FleetSafe filter here is an explainable demonstration, not the final formal proof.",
    ],
}
card_path=OUTPUT_ROOT/"model_and_dataset_card.json"
card_path.write_text(json.dumps(model_card, indent=2))
print("[SAVED]", card_path)

ckpt_path=OUTPUT_ROOT/"temporal_stop_head_checkpoint.pt"
torch.save({"model_state_dict":model.state_dict(), "feature_cols":feature_cols, "window":window, "using_synthetic_data":bool(step_df.synthetic.any()), "history":history}, ckpt_path)
print("[SAVED]", ckpt_path)

# %% [markdown]
# # 19. Commands for the real repository workflow
#
# ## Check Git working tree
#
# ```bash
# cd ~/robotics/gnm-vlnverse-baseline
# git status --short
# ```
#
# ## Run tests
#
# ```bash
# python3 -m pytest tests/gnm -q
# ```
#
# ## Run reproducibility pack
#
# ```bash
# bash scripts/gnm/run_reproducibility_pack.sh
# ```
#
# ## Launch Isaac Sim safely
#
# ```bash
# conda activate isaac
#
# unset PYTHONPATH
# unset ROS_PYTHON_VERSION
#
# export ACCEPT_EULA=Y
# export PRIVACY_CONSENT=Y
# export ROS_DOMAIN_ID=0
# export ROS_DISTRO=humble
# export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:/humble/lib"
#
# isaacsim isaacsim.exp.full
# ```
#
# ## Open Yahboom stage inside Isaac Script Editor
#
# ```python
# import omni.usd
# stage_path = "/home/favl/robotics/gnm-vlnverse-baseline/assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda"
# omni.usd.get_context().open_stage(stage_path)
# ```
#
# ## Add ROS 2 OmniGraph inside Isaac Script Editor
#
# ```python
# exec(open("/home/favl/robotics/gnm-vlnverse-baseline/scripts/gnm/add_yahboom_ros2_omnigraph.py").read())
# ```
#
# ## Check live ROS 2 topics from a second terminal
#
# ```bash
# cd ~/robotics/gnm-vlnverse-baseline
# source /opt/ros/humble/setup.bash
# export ROS_DOMAIN_ID=0
# export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
#
# ros2 topic list -t | sort
# python3 scripts/gnm/verify_yahboom_live_topics.py --strict
# ```
#
# ## Record episode_001 only after strict gate passes
#
# ```bash
# bash scripts/gnm/record_yahboom_episode_001_after_gate.sh 60
# ```
# %% [markdown]
# # 20. Final notebook summary
#
# This notebook gives me a full explainable pipeline for:
#
# - dataset loading;
# - EDA and profiling;
# - missing-value checks;
# - outlier checks;
# - correlations and heatmaps;
# - trajectory movement plots;
# - stopping method comparison;
# - temporal stop-head training;
# - FleetSafe safety-layer demonstration;
# - production commands for Isaac, ROS 2, and gated recording.
#
# The central project message is:
#
# > I am not just training a robot model. I am building a traceable, testable, and safety-gated robot navigation pipeline.
#
# The next live evidence step is to make the five Yahboom Isaac ROS 2 topics pass strict verification, then record and validate `episode_001`.
