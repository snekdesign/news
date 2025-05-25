__all__ = ('CondaUpdate',)

import asyncio
import contextlib
from typing import Annotated
from typing import cast

from annotated_types import Len
import pydantic
import pydantic_settings
import rattler
from rattler.platform.platform import PlatformLiteral
from typing_extensions import Doc

from . import _base

_CURRENT_PLATFORM = cast(PlatformLiteral, str(rattler.Platform.current()))

# Not configurable; most mirror sites don't provide nvidia channel
_MIRROR_PREFIX = 'https://mirrors.cernet.edu.cn/anaconda'

_PREFIX = 'https://conda.anaconda.org/'
_START = len(_PREFIX)


class CondaUpdate(_base.Settings):
    """Core class for checking conda repo data updates"""

    model_config = pydantic_settings.SettingsConfigDict(
        pyproject_toml_table_header=('tool', 'news', 'conda-update'),
        str_strip_whitespace=True,
        str_min_length=1,
    )

    cache_path: Annotated[
        pydantic.StrictStr,
        Doc('Where the repo data should be downloaded'),
    ]
    platforms: Annotated[
        frozenset[PlatformLiteral],
        Len(1),
        Doc('Platforms for which the repo data should be fetched'),
    ] = frozenset(('noarch', _CURRENT_PLATFORM))
    channels: Annotated[
        frozenset[pydantic.StrictStr],
        Len(1),
        Doc('Channels to fetch repo data'),
    ] = frozenset(('conda-forge',))
    specs: Annotated[
        frozenset[pydantic.StrictStr],
        Len(1),
        Doc('Queried package specifications'),
    ]
    mirrored_channels: Annotated[
        frozenset[pydantic.StrictStr],
        Doc('Channels which are mirrored at ' + _MIRROR_PREFIX),
    ] = frozenset()

    async def check(self):
        specs = [rattler.MatchSpec(spec, strict=True) for spec in self.specs]
        records = list['rattler.RepoDataRecord']()
        with contextlib.ExitStack() as stack:
            for repodata in [
                stack.enter_context(repodata)
                for repodata in await rattler.fetch_repo_data(
                    channels=list(map(rattler.Channel, self.channels)),
                    platforms=list(map(rattler.Platform, self.platforms)),
                    cache_path=self.cache_path,
                    callback=None,
                )
            ]:
                records += repodata.load_matching_records(specs)
        return records


def main():
    conda_update = CondaUpdate()
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
        print(rec.timestamp, url)


if __name__ == '__main__':
    main()
