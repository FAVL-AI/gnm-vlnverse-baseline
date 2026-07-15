# Track-B Visual Similarity Matrix (DINO ViT-S/16 cosine)

Lower = more visually distinct. Goal branches of a real junction should be < 0.6. 

| view | warehouse_multiple_shelves:p00:goalA:E | warehouse_multiple_shelves:p00:goalB:N | warehouse_multiple_shelves:p10:goalA:E | warehouse_multiple_shelves:p10:goalB:N | warehouse_multiple_shelves:p30:goalA:N | warehouse_multiple_shelves:p30:goalB:W | warehouse_multiple_shelves:p40:goalA:N | warehouse_multiple_shelves:p40:goalB:W | warehouse_multiple_shelves:p01:goalA:E | warehouse_multiple_shelves:p01:goalB:N | warehouse_multiple_shelves:p11:goalA:E | warehouse_multiple_shelves:p11:goalB:N | warehouse_multiple_shelves:p21:goalA:E | warehouse_multiple_shelves:p21:goalB:S | warehouse_multiple_shelves:p31:goalA:N | warehouse_multiple_shelves:p31:goalB:W |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| warehouse_multiple_shelves:p00:goalA:E | 1.0 | 0.682 | 0.872 | 0.647 | 0.661 | 0.862 | 0.671 | 0.931 | 0.932 | 0.659 | 0.875 | 0.602 | 0.896 | 0.554 | 0.636 | 0.856 |
| warehouse_multiple_shelves:p00:goalB:N | 0.682 | 1.0 | 0.645 | 0.914 | 0.929 | 0.636 | 0.954 | 0.651 | 0.651 | 0.91 | 0.618 | 0.825 | 0.634 | 0.546 | 0.846 | 0.635 |
| warehouse_multiple_shelves:p10:goalA:E | 0.872 | 0.645 | 1.0 | 0.621 | 0.629 | 0.933 | 0.638 | 0.878 | 0.845 | 0.619 | 0.9 | 0.596 | 0.87 | 0.616 | 0.625 | 0.863 |
| warehouse_multiple_shelves:p10:goalB:N | 0.647 | 0.914 | 0.621 | 1.0 | 0.93 | 0.601 | 0.882 | 0.61 | 0.623 | 0.834 | 0.592 | 0.897 | 0.589 | 0.549 | 0.886 | 0.6 |
| warehouse_multiple_shelves:p30:goalA:N | 0.661 | 0.929 | 0.629 | 0.93 | 1.0 | 0.628 | 0.94 | 0.641 | 0.649 | 0.856 | 0.604 | 0.836 | 0.606 | 0.554 | 0.893 | 0.63 |
| warehouse_multiple_shelves:p30:goalB:W | 0.862 | 0.636 | 0.933 | 0.601 | 0.628 | 1.0 | 0.635 | 0.921 | 0.837 | 0.633 | 0.87 | 0.592 | 0.854 | 0.631 | 0.621 | 0.921 |
| warehouse_multiple_shelves:p40:goalA:N | 0.671 | 0.954 | 0.638 | 0.882 | 0.94 | 0.635 | 1.0 | 0.659 | 0.648 | 0.889 | 0.619 | 0.789 | 0.627 | 0.561 | 0.853 | 0.647 |
| warehouse_multiple_shelves:p40:goalB:W | 0.931 | 0.651 | 0.878 | 0.61 | 0.641 | 0.921 | 0.659 | 1.0 | 0.889 | 0.647 | 0.866 | 0.588 | 0.871 | 0.584 | 0.637 | 0.892 |
| warehouse_multiple_shelves:p01:goalA:E | 0.932 | 0.651 | 0.845 | 0.623 | 0.649 | 0.837 | 0.648 | 0.889 | 1.0 | 0.616 | 0.872 | 0.583 | 0.874 | 0.556 | 0.614 | 0.871 |
| warehouse_multiple_shelves:p01:goalB:N | 0.659 | 0.91 | 0.619 | 0.834 | 0.856 | 0.633 | 0.889 | 0.647 | 0.616 | 1.0 | 0.576 | 0.82 | 0.604 | 0.553 | 0.83 | 0.609 |
| warehouse_multiple_shelves:p11:goalA:E | 0.875 | 0.618 | 0.9 | 0.592 | 0.604 | 0.87 | 0.619 | 0.866 | 0.872 | 0.576 | 1.0 | 0.548 | 0.903 | 0.588 | 0.567 | 0.935 |
| warehouse_multiple_shelves:p11:goalB:N | 0.602 | 0.825 | 0.596 | 0.897 | 0.836 | 0.592 | 0.789 | 0.588 | 0.583 | 0.82 | 0.548 | 1.0 | 0.537 | 0.552 | 0.924 | 0.576 |
| warehouse_multiple_shelves:p21:goalA:E | 0.896 | 0.634 | 0.87 | 0.589 | 0.606 | 0.854 | 0.627 | 0.871 | 0.874 | 0.604 | 0.903 | 0.537 | 1.0 | 0.528 | 0.56 | 0.874 |
| warehouse_multiple_shelves:p21:goalB:S | 0.554 | 0.546 | 0.616 | 0.549 | 0.554 | 0.631 | 0.561 | 0.584 | 0.556 | 0.553 | 0.588 | 0.552 | 0.528 | 1.0 | 0.592 | 0.616 |
| warehouse_multiple_shelves:p31:goalA:N | 0.636 | 0.846 | 0.625 | 0.886 | 0.893 | 0.621 | 0.853 | 0.637 | 0.614 | 0.83 | 0.567 | 0.924 | 0.56 | 0.592 | 1.0 | 0.601 |
| warehouse_multiple_shelves:p31:goalB:W | 0.856 | 0.635 | 0.863 | 0.6 | 0.63 | 0.921 | 0.647 | 0.892 | 0.871 | 0.609 | 0.935 | 0.576 | 0.874 | 0.616 | 0.601 | 1.0 |
