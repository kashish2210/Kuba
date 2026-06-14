from whitenoise.storage import CompressedManifestStaticFilesStorage


class RelaxedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """WhiteNoise manifest storage that tolerates missing referenced files.

    Third-party packages (e.g. jazzmin's bundled Bootstrap) ship minified JS/CSS
    with ``sourceMappingURL`` comments pointing at ``.map`` files that aren't
    included. Django's default storage tries to resolve those references during
    ``collectstatic`` post-processing and raises ``MissingFileError``.

    We drop the ``sourceMappingURL`` rewrite patterns (those maps are never
    served) while keeping the important CSS ``url()`` / ``@import`` rewriting,
    and disable strict manifest lookups at runtime.
    """

    manifest_strict = False

    patterns = (
        (
            "*.css",
            (
                r"""(?P<matched>url\(['"]{0,1}\s*(?P<url>.*?)["']{0,1}\))""",
                (
                    r"""(?P<matched>@import\s*["']\s*(?P<url>.*?)["'])""",
                    """@import url("%(url)s")""",
                ),
            ),
        ),
    )
