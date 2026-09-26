# Anatomical trait vocabulary

Edit `traits.tsv` to refine a species. Each row contains its FireRed symbol, body-plan key, primary color, ordered signature features, and an optional fifth field with a more specific body description. Features have attachment slots, such as `ears`, `face`, `tail`, `wings`, and `markings`. Earlier features are considered more characteristic. Descriptions are hand-authored visual design judgments and should be reviewed against the species artwork when refined.

There are 386 unique species profiles. Legacy Unown entries resolve to the Unown profile; their exact glyph geometry is not modeled. A few canonical multi-headed or multi-armed species have explicit native-body descriptions in `companion/anatomy.py`. Donors cannot independently add extra complete heads or bodies.

`python -m scripts.export_traits` exports the resolved table to `build/trait-catalog/TRAITS.md` and `traits.json`. Species IDs come from the pinned FireRed source catalog, rather than assuming that internal IDs equal National Dex numbers.

The compiler reserves one lineage signature and chooses up to three additional nonconflicting traits. Donors with at least 10% weight each get a selection opportunity before spare slots are filled by overall score. A head crest and a pair of ears compete for the crown region; back ornaments and wings compete for the back region. All contributors affect continuous body dimensions and the sketch palette, even if too small to supply a signature trait. Four signatures and a 2.5% minimum visible-feature weight keep small sprites readable. These are adjustable art heuristics, not guarantees about image-model behavior.

An edited trait file changes the generation cache key. Restart the companion after editing it. The immutable battle history and previous sprite files remain intact.
