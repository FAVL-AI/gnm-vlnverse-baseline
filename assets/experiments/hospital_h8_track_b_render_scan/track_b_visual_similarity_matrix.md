# Track-B Visual Similarity Matrix (DINO ViT-S/16 cosine)

Lower = more visually distinct. Goal branches of a real junction should be < 0.6. 

| view | office_isaac:p03:goalA:N | office_isaac:p03:goalB:S | warehouse_simple:p00:goalA:N | warehouse_simple:p00:goalB:E | warehouse_simple:p10:goalA:N | warehouse_simple:p10:goalB:E | warehouse_simple:p20:goalA:N | warehouse_simple:p20:goalB:W | warehouse_simple:p30:goalA:N | warehouse_simple:p30:goalB:W | warehouse_simple:p01:goalA:N | warehouse_simple:p01:goalB:E | warehouse_simple:p11:goalA:N | warehouse_simple:p11:goalB:S | warehouse_simple:p21:goalA:N | warehouse_simple:p21:goalB:S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| office_isaac:p03:goalA:N | 1.0 | 0.674 | 0.415 | 0.387 | 0.437 | 0.344 | 0.434 | 0.343 | 0.461 | 0.344 | 0.391 | 0.39 | 0.39 | 0.32 | 0.406 | 0.307 |
| office_isaac:p03:goalB:S | 0.674 | 1.0 | 0.477 | 0.522 | 0.525 | 0.462 | 0.569 | 0.361 | 0.599 | 0.376 | 0.449 | 0.48 | 0.536 | 0.487 | 0.548 | 0.483 |
| warehouse_simple:p00:goalA:N | 0.415 | 0.477 | 1.0 | 0.695 | 0.899 | 0.706 | 0.787 | 0.703 | 0.779 | 0.696 | 0.939 | 0.661 | 0.794 | 0.681 | 0.765 | 0.657 |
| warehouse_simple:p00:goalB:E | 0.387 | 0.522 | 0.695 | 1.0 | 0.778 | 0.917 | 0.844 | 0.748 | 0.869 | 0.761 | 0.695 | 0.938 | 0.799 | 0.766 | 0.804 | 0.754 |
| warehouse_simple:p10:goalA:N | 0.437 | 0.525 | 0.899 | 0.778 | 1.0 | 0.777 | 0.919 | 0.696 | 0.888 | 0.696 | 0.909 | 0.743 | 0.901 | 0.781 | 0.882 | 0.761 |
| warehouse_simple:p10:goalB:E | 0.344 | 0.462 | 0.706 | 0.917 | 0.777 | 1.0 | 0.828 | 0.786 | 0.852 | 0.773 | 0.702 | 0.893 | 0.817 | 0.776 | 0.794 | 0.765 |
| warehouse_simple:p20:goalA:N | 0.434 | 0.569 | 0.787 | 0.844 | 0.919 | 0.828 | 1.0 | 0.704 | 0.961 | 0.714 | 0.806 | 0.823 | 0.924 | 0.815 | 0.935 | 0.809 |
| warehouse_simple:p20:goalB:W | 0.343 | 0.361 | 0.703 | 0.748 | 0.696 | 0.786 | 0.704 | 1.0 | 0.709 | 0.965 | 0.661 | 0.763 | 0.672 | 0.652 | 0.667 | 0.649 |
| warehouse_simple:p30:goalA:N | 0.461 | 0.599 | 0.779 | 0.869 | 0.888 | 0.852 | 0.961 | 0.709 | 1.0 | 0.707 | 0.77 | 0.84 | 0.879 | 0.819 | 0.9 | 0.818 |
| warehouse_simple:p30:goalB:W | 0.344 | 0.376 | 0.696 | 0.761 | 0.696 | 0.773 | 0.714 | 0.965 | 0.707 | 1.0 | 0.658 | 0.774 | 0.67 | 0.643 | 0.67 | 0.64 |
| warehouse_simple:p01:goalA:N | 0.391 | 0.449 | 0.939 | 0.695 | 0.909 | 0.702 | 0.806 | 0.661 | 0.77 | 0.658 | 1.0 | 0.65 | 0.846 | 0.69 | 0.817 | 0.667 |
| warehouse_simple:p01:goalB:E | 0.39 | 0.48 | 0.661 | 0.938 | 0.743 | 0.893 | 0.823 | 0.763 | 0.84 | 0.774 | 0.65 | 1.0 | 0.77 | 0.758 | 0.772 | 0.749 |
| warehouse_simple:p11:goalA:N | 0.39 | 0.536 | 0.794 | 0.799 | 0.901 | 0.817 | 0.924 | 0.672 | 0.879 | 0.67 | 0.846 | 0.77 | 1.0 | 0.849 | 0.955 | 0.833 |
| warehouse_simple:p11:goalB:S | 0.32 | 0.487 | 0.681 | 0.766 | 0.781 | 0.776 | 0.815 | 0.652 | 0.819 | 0.643 | 0.69 | 0.758 | 0.849 | 1.0 | 0.841 | 0.984 |
| warehouse_simple:p21:goalA:N | 0.406 | 0.548 | 0.765 | 0.804 | 0.882 | 0.794 | 0.935 | 0.667 | 0.9 | 0.67 | 0.817 | 0.772 | 0.955 | 0.841 | 1.0 | 0.842 |
| warehouse_simple:p21:goalB:S | 0.307 | 0.483 | 0.657 | 0.754 | 0.761 | 0.765 | 0.809 | 0.649 | 0.818 | 0.64 | 0.667 | 0.749 | 0.833 | 0.984 | 0.842 | 1.0 |
