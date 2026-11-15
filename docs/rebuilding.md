# Which component actually needs rebuilding

`build.sh` rebuilds whatever it is told to. It cannot know whether that is
*necessary*, and rebuilding everything "to be safe" costs hours of LTO on a
machine with no swap. This file is the measurement that decides, and the
measurement that proves the result.

## The question, and the only honest way to answer it

A component is stale when **a patch in its series is newer than the `.deb`
the image ships**. Not when the series changed - when *its own* series did.
The series are per source package (`patches/<source>/`), so the two
components go stale independently.

```sh
# the newest commit date of every patch, series by series
for p in patches/*/*.patch; do
    printf '%-18s %-62s ' "$(basename "$(dirname "$p")")" "$(basename "$p")"
    git log -1 --format='%ad' --date=format:'%Y-%m-%d %H:%M' -- "$p"
done

# and when each shipped package was produced
ls -la --time-style=+'%Y-%m-%d %H:%M' /var/tmp/raye/desktop-debs/
```

A patch dated **after** the packages means that component is stale. A patch
dated before means a rebuild would produce the same bytes, and the hours buy
nothing.

## The trap: one build log does not mean one build

Measured 2026-11-07. All eighteen `.deb` in `/var/tmp/raye/desktop-debs/`
carried the same timestamp, **2026-11-06 01:30**, which reads exactly like a
single run that built both components. The build logs in the chroot say
otherwise:

```
build-full.log   Building plasma-desktop 4:6.6.6-0ubuntu0.1+raye1
build3.log       Building plasma-desktop 4:6.6.6-0ubuntu0.1+raye1
build4.log       Building plasma-desktop 4:6.6.6-0ubuntu0.1+raye1
```

**Not one of the three built `plasma-workspace`.** The identical timestamp is
the `mv` into the output folder, not the build. So the timestamp tells you
when a package arrived, never which run produced it or what that run
contained - and `grep -o "Building [a-z-]*"` over the logs is what answers
that.

## What that measurement decided, 2026-11-07

| series | newest patch | shipped `.deb` | verdict |
|---|---|---|---|
| `plasma-desktop` | 2026-11-05 21:12 | 2026-11-06 01:30 | **up to date** |
| `plasma-workspace` | **2026-11-06 10:49** | 2026-11-06 01:30 | **stale by two patches** |

The two late patches are `0002-the-session-reads-rayes-own-application-menu`
(10:26) and `0003-the-notification-area-draws-its-icons-at-16-px` (10:49).
So `plasma-workspace` alone was rebuilt - half the work, and the half that
changes the image.

## Proving the rebuild landed, not assuming it

A patch that applies is not a patch that shipped: the file can be added to
the source and still be absent from the package, because the package ships
what its install rules name. The check is the package's own contents.

```sh
dpkg-deb -c out/plasma-workspace_*_amd64.deb | grep RayeTrayMetrics
```

Measured on the **old** package: `0`. That is the shape of the defect this
file exists to prevent - an image rebuilt from stale packages boots, looks
right, and still never reads Raye's application menu.

## Running it

`build.sh` needs root in a resolute system with `deb-src`. The chroot at
`/var/tmp/raye/agents` is that system; it is **not** scratch, and deleting it
destroys the build environment.

```sh
c=/var/tmp/raye/agents
mkdir -p "$c/srv/raye/desktop"
mount --bind -o ro /srv/raye/desktop "$c/srv/raye/desktop"
chroot "$c" /bin/sh -c 'cd /srv/raye/desktop &&
    JOBS=24 WORK=$HOME/dw OUT=$HOME/out ./build.sh plasma-workspace'
```

**`JOBS=24`, and the number is measured, not chosen.** The host has 28
cores, 31 GB of RAM and **no swap**; the default `JOBS` is `nproc`, and
unbounded parallelism is what gets `lto1` killed (see
`tests/test_build_guards.py`). 24 is the value the build of 2026-11-05
completed with on this same host. Lowering memory use with `-flto=N` instead
is refused by `build.sh`, and the reason is in its own comment: it changes
which symbols the libraries export.

The mount is **read-only** and `WORK`/`OUT` point outside the repository.
A file created in `/srv` from the build machine is born `root:root`, and the
services that read `/srv` run as uid 1000.
