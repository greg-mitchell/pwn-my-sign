# Provenance and licensing

## Independent implementation

The Python sender and encoder were implemented from observations of Bluetooth
traffic between the owner's phone and sign. No Dory app source, decompiled code,
firmware, signing keys, or authentication tokens were used or are distributed.
The protocol document describes the observed interface and its limits.

Implementation and documentation were developed with AI assistance and reviewed
through offline tests and physical upload experiments.

## Images and fonts

Public fixtures are independently constructed grayscale and checkerboard bytes.
`scripts/generate_test_fixtures.py` regenerates them without using the encoder,
Dory's app, font files, or artwork.

The diagnostic image utility loads a font supplied by the user or already present
on their system. It does not distribute that font. Use appropriately licensed
fonts and artwork for any assets you choose to share.

## Project and dependency licenses

The project code and documentation use the [MIT License](../LICENSE.txt).
That license applies to the project's material; third-party dependencies and
product names retain their own rights and terms.

The installed runtime metadata reviewed on 2026-10-22 reports:

| Dependency | Version reviewed | Declared license |
| --- | --- | --- |
| Click | 8.5.0 | BSD-3-Clause |
| Bleak | 3.0.1 | MIT |
| Pillow | 12.3.0 | MIT-CMU |
| PyObjC runtime/framework packages on macOS | 12.2.2 | MIT |

Dependencies are installed separately by `uv`; their source and binary
distributions supply their own license notices. This table is not a complete
inventory of development tools, optional investigation dependencies, or bundled
libraries inside third-party wheels. A future bundled application must review
and retain notices for everything it redistributes.

## Product identity and private evidence

This project is independent and is not affiliated with or endorsed by Dory AS or
GitHub. Product names are used to identify compatible hardware and data sources.
The repository does not distribute their logos or app assets.