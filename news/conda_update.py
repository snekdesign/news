__all__ = ('CondaUpdate',)

import asyncio
import collections
from typing import Annotated
from typing import cast
from typing import TYPE_CHECKING

from annotated_types import Len
import pydantic
import pydantic_settings
import rattler
from rattler.platform.platform import PlatformLiteral
from typing_extensions import Doc

if TYPE_CHECKING:
    class _CondaMatchSpec:
        def __init__(self, __spec: str) -> None: ...
        def __contains__(self, field: str) -> bool: ...
        def match(self, rec: rattler.RepoDataRecord) -> bool: ...
else:
    from conda.models.match_spec import MatchSpec as _CondaMatchSpec

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
        specs_by_name = collections.defaultdict[
            'rattler.PackageName',
            'list[tuple[rattler.MatchSpec, _CondaMatchSpec | None]]',
        ](list)
        # BUG: in py-rattler<=0.7.0 (maybe later):
        # - rattler.MatchSpec() rejects `[channel=xxx]`
        # - rattler.MatchSpec.matches() ignores channel
        for conda_spec in set(map(_CondaMatchSpec, self.specs)):
            # Convert `[channel=xxx]` to `channel::`
            spec = str(conda_spec)
            rattler_spec = rattler.MatchSpec(spec)
            if pkg_name := rattler_spec.name:
                if 'channel' in conda_spec:
                    spec = spec[: spec.rindex(':')+1] + '*'
                    conda_spec = _CondaMatchSpec(spec)
                else:
                    conda_spec = None
                specs_by_name[pkg_name].append((rattler_spec, conda_spec))
        records = list['rattler.RepoDataRecord']()
        for repodata in await rattler.fetch_repo_data(
            channels=list(map(rattler.Channel, self.channels)),
            platforms=list(map(rattler.Platform, self.platforms)),
            cache_path=self.cache_path,
            callback=None,
        ):
            for pkg_name, specs in specs_by_name.items():
                for rec in repodata.load_records(pkg_name):
                    for rattler_spec, conda_spec in specs:
                        if rattler_spec.matches(rec) and (
                            not conda_spec or conda_spec.match(rec)
                        ):
                            records.append(rec)
                            break
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
