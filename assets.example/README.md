# Example assets

Placeholder images referenced by [`../project.example.toml`](../project.example.toml). Replace them with
your real PiP backgrounds and holding/title slides (any format Resolve imports — PNG, JPEG, EXR, MOV, …).
The tiny PNGs here just exist so the example config imports cleanly.

- `backgrounds/` — full-frame looks sat behind picture-in-picture.
- `slides/` — holding cards and title slides.

Each file is placed into a media-pool bin by an `[[assets]]` entry in the config, not by its folder here.
