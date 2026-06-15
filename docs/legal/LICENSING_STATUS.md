# Licensing Status

**Date reviewed:** 2026-06-15  
**Repository:** FAVL-AI/gnm-vlnverse-baseline  
**Branch:** track-b-language-grounding

## Current status

No top-level open-source licence has been formally selected for this repository.
The `pyproject.toml` file declares:

```
license = { text = "All rights reserved. See COPYRIGHT.md and docs/legal/LICENSING_STATUS.md." }
```

No `LICENSE` file exists at the repository root. This means:

- All rights are reserved to the original author under UK copyright law by default.
- Public visibility of this repository on GitHub does not constitute permission to
  reuse, reproduce, distribute or adapt the code.
- See `COPYRIGHT.md` for the full copyright notice.

## Compatibility constraints

Before selecting a licence, the following upsteam licences must be confirmed as
compatible:

| Dependency | Licence (known) | Status |
|------------|-----------------|--------|
| VLNTube (external/VLNTube/) | MIT | Compatible with most licences |
| VisualNav-Transformer (third_party/) | LICENCE_REVIEW_REQUIRED | Unknown |
| IAmGoodNavigator (external/) | LICENCE_REVIEW_REQUIRED | Unknown |
| Eyz/VLNVerse_data (HuggingFace) | LICENCE_REVIEW_REQUIRED | Unknown |
| Eyz/VLNVerse_scene (HuggingFace) | LICENCE_REVIEW_REQUIRED | Unknown |
| CLIP weights (openai/clip-vit-base-patch16) | MIT | Compatible |
| PyTorch | BSD-3-Clause | Compatible |
| NVIDIA Isaac Sim | NVIDIA EULA | Restrictive; check redistribution |

## Recommended next steps

1. Confirm the licence of `Eyz/VLNVerse_data` and `Eyz/VLNVerse_scene` via the
   HuggingFace dataset cards or contact with V3A Group.
2. Confirm the licence of `third_party/visualnav-transformer` (upstream is
   https://github.com/robodhruv/visualnav-transformer).
3. Verify that Newcastle University's IP policy does not restrict the choice of
   open-source licence for this doctoral research.
4. Once compatibility is confirmed, select a licence, add a `LICENSE` file, and
   update the `pyproject.toml` licence declaration accordingly.

## Reference

Newcastle University IP policy:
https://www.ncl.ac.uk/mediav8/our-research/research-governance-policies/NU_IP_policy%20June_2024.pdf

UK copyright law (Crown copyright guidance):
https://www.gov.uk/guidance/the-rights-granted-by-copyright
