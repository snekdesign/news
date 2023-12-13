__all__ = ('CondaUpdate',)

import argparse
import asyncio
from collections.abc import Callable
from collections.abc import Iterator
import datetime
import itertools
import operator
from typing import Annotated
from typing import TextIO

from annotated_types import Len
import conda.models.match_spec as conda
import pydantic
from pydantic import StringConstraints
import rattler
from rattler.platform.platform import PlatformLiteral
from typing_extensions import Doc
import yaml

# Not configurable; most mirror sites don't provide nvidia channel
_MIRROR_PREFIX = 'https://mirrors.cernet.edu.cn/anaconda'

_PREFIX = 'https://conda.anaconda.org/'
_START = len(_PREFIX)

_Str = Annotated[str, StringConstraints(strict=True, min_length=1)]
_Strs = frozenset[Annotated[_Str, StringConstraints(strip_whitespace=True)]]


class CondaUpdate(pydantic.BaseModel):
    """Core class for checking conda repo data updates"""

    cache_path: Annotated[
        _Str,
        Doc('Where the repo data should be downloaded'),
    ]
    platforms: Annotated[
        frozenset[PlatformLiteral],
        Len(1),
        Doc('Platforms for which the repo data should be fetched'),
    ]
    channels: Annotated[_Strs, Len(1), Doc('Channels to fetch repo data')]
    specs: Annotated[_Strs, Len(1), Doc('Queried package specifications')]
    mirrored_channels: Annotated[
        _Strs,
        Doc('Channels which are mirrored at ' + _MIRROR_PREFIX),
    ] = frozenset()

    async def check(self) -> Iterator[rattler.RepoDataRecord]:
        return itertools.chain.from_iterable(
            itertools.starmap(
                operator.call,
                itertools.product(
                    map(_make_filter, self.specs),
                    await rattler.fetch_repo_data(
                        channels=list(map(rattler.Channel, self.channels)),
                        platforms=list(map(rattler.Platform, self.platforms)),
                        cache_path=self.cache_path,
                        callback=None,
                    ),
                ),
            ),
        )


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=argparse.FileType(encoding='utf-8'))
    with parser.parse_args(namespace=_Namespace()).config as f:
        conda_update = CondaUpdate.model_validate(yaml.safe_load(f))

    records = asyncio.run(conda_update.check())

    mirrors = {
        f'{c}/': f'{_MIRROR_PREFIX}/cloud/{c}/'
        for c in conda_update.mirrored_channels
    }
    mirrors.setdefault('nvidia/', f'{_MIRROR_PREFIX}-extra/cloud/nvidia/')
    prefixes = tuple(mirrors)

    for rec in records:
        url = rec.url
        if url.startswith(_PREFIX) and url.startswith(prefixes, _START):
            sep = url.index('/', _START) + 1
            url = mirrors[url[_START:sep]] + url[sep:]
        if ts := rec.timestamp:
            print(datetime.date.fromtimestamp(ts), url)
        else:
            print(url)


def _make_filter(spec: str) -> Callable[
    [rattler.SparseRepoData],
    Iterator[rattler.RepoDataRecord],
]:
    conda_spec = conda.MatchSpec(spec)
    pkg_name = rattler.PackageName(conda_spec.name)
    # BUG: in py-rattler<=0.2.0 (maybe later):
    # - rattler.MatchSpec() rejects `[channel=xxx]`
    # - rattler.MatchSpec.matches() ignores channel
    if 'channel' in conda_spec:
        # Convert `[channel=xxx]` to `channel::`
        spec = str(conda_spec)
        conda_spec = conda.MatchSpec(spec[:spec.rindex(':')+1]+'*')

        def record_filter(repo: rattler.SparseRepoData):
            return filter(
                conda_spec.match,
                filter(rattler_spec.matches, repo.load_records(pkg_name)),
            )
    else:
        def record_filter(repo: rattler.SparseRepoData):
            return filter(rattler_spec.matches, repo.load_records(pkg_name))

    rattler_spec = rattler.MatchSpec(spec)
    return record_filter


class _Namespace:
    config: TextIO


if __name__ == '__main__':
    _main()
