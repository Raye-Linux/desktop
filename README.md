# Raye desktop

Raye's own builds of the desktop packages: Ubuntu's sources with a short
Raye patch series on top. What Raye changes in how the desktop behaves
lives in the desktop's code here, not in scripts layered over it. How it
looks lives in the theme repository.

- `components` the packages this repo rebuilds, and their versions
- `patches/<package>/` the patch series of each one
- `revisions` the Raye revision of each package
- `tests/` checks that run without building anything

## Build

    ./fetch-sources.sh            # downloads the sources (needs deb-src)
    ./build.sh                    # every component
    ./build.sh plasma-desktop     # one of them

The build runs in an Ubuntu resolute system and takes a while: only
rebuild what a patch touches.

## Test

    pytest tests/

## License

GPL-2.0, like the desktop it patches (`LICENSE`).

## Links

- Website: https://rayelinux.com
- Discord: https://discord.gg/TrxhUkabyB (questions, bug reports, news)
