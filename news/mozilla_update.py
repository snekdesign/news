__all__ = ('MozillaUpdate',)

from typing import Literal

import mozdownload
import pydantic
import pydantic_settings

from . import _base


class _Spec(pydantic.BaseModel):
    """Run `mozdownload -h` for documentation"""

    application: Literal['firefox', 'thunderbird'] = 'firefox'
    extension: str = ''
    locale: str = ''


class MozillaUpdate(_base.Settings):
    model_config = pydantic_settings.SettingsConfigDict(
        pyproject_toml_table_header=('tool', 'news', 'mozilla-update'),
        strict=True,
        str_strip_whitespace=True,
    )

    specs: list[_Spec] = []


def main():
    for spec in MozillaUpdate().specs:
        scraper = mozdownload.FactoryScraper(
            scraper_type='release',
            application=spec.application,
            extension=spec.extension,
            locale=spec.locale,
            version='latest',
        )
        print(scraper.url)


if __name__ == '__main__':
    main()
