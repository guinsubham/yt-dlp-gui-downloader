# Third-Party Notices

The MIT License in this repository applies only to the original application source and assets. The application bundles or downloads the components below under their respective terms. License texts for bundled Python components are distributed in `third_party_licenses`.

## Bundled runtime components

| Component | Version | License | Source |
| --- | --- | --- | --- |
| yt-dlp | 2026.6.9 | Unlicense | <https://github.com/yt-dlp/yt-dlp> |
| yt-dlp EJS | 0.8.0 | Unlicense, MIT, and ISC | <https://github.com/yt-dlp/ejs> |
| Brotli | 1.2.0 | MIT | <https://github.com/google/brotli> |
| certifi | 2026.5.20 | MPL-2.0 | <https://github.com/certifi/python-certifi> |
| charset-normalizer | 3.4.7 | MIT | <https://github.com/jawah/charset_normalizer> |
| idna | 3.17 | BSD-3-Clause | <https://github.com/kjd/idna> |
| Pillow | 12.3.0 | HPND | <https://github.com/python-pillow/Pillow> |
| PyCryptodomeX | 3.23.0 | BSD-2-Clause and public-domain components | <https://github.com/Legrandin/pycryptodome> |
| Requests | 2.34.2 | Apache-2.0 | <https://github.com/psf/requests> |
| urllib3 | 2.7.0 | MIT | <https://github.com/urllib3/urllib3> |
| websockets | 16.0 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| PyInstaller bootloader | 6.20.0 | GPL-2.0 with a distribution exception | <https://github.com/pyinstaller/pyinstaller> |

## Downloaded first-run components

These executables are downloaded separately after installation and are not covered by this application's MIT License.

| Component | License | Binary source | Corresponding source |
| --- | --- | --- | --- |
| Deno | MIT | <https://github.com/denoland/deno/releases> | <https://github.com/denoland/deno> |
| FFmpeg LGPL build | LGPL-3.0-or-later | <https://github.com/BtbN/FFmpeg-Builds/releases> | <https://github.com/FFmpeg/FFmpeg> |

The app selects the explicitly labeled LGPL Windows build, preserves the license supplied in its archive, and invokes it as a separate process. Release metadata, file size, and SHA-256 digest are verified before either first-run component is installed.
