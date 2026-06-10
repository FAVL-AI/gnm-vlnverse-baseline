"""gnm_vlnverse — General Navigation Model inside VLNVerse/Isaac Sim.

Tracks
------
A  GNM visual-goal reproduction   RGB + visual goal
B  Strict text-only VLN + GNM     RGB + language
C  Visual-reference VLN + GNM     RGB + language + reference image
D  LoRA-adapted GNM               Same inputs as A/B/C, adapted weights
"""

__version__ = "0.1.0"
