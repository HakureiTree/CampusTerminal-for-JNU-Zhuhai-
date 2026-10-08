# Third-Party Source

CampusAuth's H3C protocol encoding and AES/MD5 transform are adaptations of
[Besfim/inode-njit](https://github.com/Besfim/inode-njit), pinned at commit
`7e984256e20e5d6325643fb79daab895ffc6cad7`.

Original source, attribution and license are retained in `vendor/inode-njit`.
The license text is `vendor/inode-njit/License/gpl-3.0.txt`.
The new CampusAuth source is licensed under GPL-3.0-or-later.
Distributions must retain the license and provide corresponding source.

Adapted files: `src/auth.c`, `src/h3c_AES_MD5.c` and its protocol documentation.
Embedded unmodified data: `src/h3c_dict.h` (40 entries), SHA-256:
`C5EDE6A8B3CC3C5C53147900512911F583D6439F451B51F3F0421E353455C4E1`.
Embedded bytes are lookup data only, never loaded as executable code.

Important difference: upstream's documented 7.0 crypto example uses dictionary
keys absent from its shipped 7.1 dictionary. Tests use an isolated lookup fixture
containing only the documented example entries. Production rejects missing keys;
it does not use upstream's fallback-to-last-entry behavior.

No iNode executable, installer contents, real credential, or local authentication
capture is embedded in the application. This is not an official H3C/JNU client.
