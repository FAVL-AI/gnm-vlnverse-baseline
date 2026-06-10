"""Unit tests for GNM model architecture.

These tests verify:
  - Forward pass produces correct output shapes
  - Parameter counts are in the expected range
  - LoRA injection changes the right parameters
  - Encoder freeze/unfreeze works correctly
  - Output is differentiable (gradients flow through)
"""
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="torch not installed; skipping model tests")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.models.gnm import GNM, build_gnm
from gnm_vlnverse.models.lora import (
    count_lora_params,
    freeze_non_lora,
    inject_lora,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def default_model():
    return GNM(
        context_size  = 5,
        goal_conditioned = True,
        action_dim    = 2,
        hidden_dim    = 256,
        encoder       = "mobilenet",
        out_dim       = 512,
        pretrained    = False,
    )


@pytest.fixture
def batch():
    B = 4
    C = 5       # context_size
    H = W = 96  # image size
    obs  = torch.randn(B, C * 3, H, W)   # stacked context
    goal = torch.randn(B, 3, H, W)
    return obs, goal


# ── Shape tests ───────────────────────────────────────────────────────────────

class TestGNMShapes:
    def test_forward_dist_shape(self, default_model, batch):
        obs, goal = batch
        dist, action = default_model(obs, goal)
        assert dist.shape == (4, 1), f"Expected (4,1), got {dist.shape}"

    def test_forward_action_shape(self, default_model, batch):
        obs, goal = batch
        dist, action = default_model(obs, goal)
        assert action.shape == (4, 2), f"Expected (4,2), got {action.shape}"

    def test_batch_size_1(self, default_model):
        obs  = torch.randn(1, 5 * 3, 96, 96)
        goal = torch.randn(1, 3, 96, 96)
        dist, action = default_model(obs, goal)
        assert dist.shape   == (1, 1)
        assert action.shape == (1, 2)

    def test_action_dim_3(self):
        model = GNM(context_size=3, action_dim=3, pretrained=False)
        obs   = torch.randn(2, 9, 96, 96)
        goal  = torch.randn(2, 3, 96, 96)
        _, action = model(obs, goal)
        assert action.shape == (2, 3)

    def test_context_size_1(self):
        model = GNM(context_size=1, pretrained=False)
        obs   = torch.randn(2, 3, 96, 96)
        goal  = torch.randn(2, 3, 96, 96)
        dist, action = model(obs, goal)
        assert dist.shape   == (2, 1)
        assert action.shape == (2, 2)


# ── Parameter count tests ─────────────────────────────────────────────────────

class TestParameterCounts:
    def test_total_params_reasonable(self, default_model):
        info = default_model.count_parameters()
        # GNM with MobileNetV2 should be ~6-8M params
        assert 3e6 < info["total"] < 15e6, f"Unexpected param count: {info['total']}"

    def test_encoder_larger_than_heads(self, default_model):
        info = default_model.count_parameters()
        assert info["encoder"] > info["heads"], (
            f"Encoder ({info['encoder']}) should be larger than heads ({info['heads']})"
        )

    def test_build_gnm_from_cfg(self):
        cfg = {
            "context_size": 5,
            "goal_conditioned": True,
            "action_dim": 2,
            "hidden_dim": 256,
            "encoder": "mobilenet",
            "out_dim": 512,
            "pretrained": False,
        }
        model = build_gnm(cfg)
        assert isinstance(model, GNM)


# ── Gradient flow tests ───────────────────────────────────────────────────────

class TestGradients:
    def test_dist_head_gradient(self, default_model, batch):
        obs, goal = batch
        dist, _   = default_model(obs, goal)
        loss      = dist.mean()
        loss.backward()
        for name, p in default_model.named_parameters():
            if "dist_predictor" in name and p.requires_grad:
                assert p.grad is not None, f"No gradient for {name}"
                break

    def test_action_head_gradient(self, default_model, batch):
        obs, goal = batch
        _, action = default_model(obs, goal)
        loss      = action.mean()
        loss.backward()
        for name, p in default_model.named_parameters():
            if "action_predictor" in name and p.requires_grad:
                assert p.grad is not None, f"No gradient for {name}"
                break


# ── Freeze/unfreeze tests ─────────────────────────────────────────────────────

class TestFreeze:
    def test_freeze_encoder(self, default_model):
        default_model.freeze_encoder()
        for name, p in default_model.named_parameters():
            if "encoder" in name:
                assert not p.requires_grad, f"{name} should be frozen"

    def test_unfreeze_heads(self, default_model):
        default_model.freeze_encoder()
        default_model.unfreeze_heads()
        for name, p in default_model.named_parameters():
            if "predictor" in name:
                assert p.requires_grad, f"{name} should be trainable"


# ── LoRA tests ────────────────────────────────────────────────────────────────

class TestLoRA:
    def test_inject_reduces_trainable_params(self, default_model):
        total_before = sum(p.numel() for p in default_model.parameters())
        inject_lora(default_model, target_modules=[r"encoder\.proj"], rank=4, alpha=8.0)
        freeze_non_lora(default_model)
        trainable = sum(p.numel() for p in default_model.parameters() if p.requires_grad)
        assert trainable < total_before, "LoRA freeze should reduce trainable params"

    def test_lora_output_shape_unchanged(self, default_model, batch):
        obs, goal = batch
        inject_lora(default_model, target_modules=[r"encoder\.proj"], rank=4, alpha=8.0)
        dist, action = default_model(obs, goal)
        assert dist.shape   == (4, 1)
        assert action.shape == (4, 2)

    def test_count_lora_params(self, default_model):
        inject_lora(default_model, target_modules=[r"encoder\.proj"], rank=4, alpha=8.0)
        info = count_lora_params(default_model)
        assert info["lora_only"] > 0
        assert 0 < info["pct"] < 100
