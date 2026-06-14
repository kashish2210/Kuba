from whitenoise.storage import CompressedManifestStaticFilesStorage


class RelaxedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    # Don't raise an error when a referenced file (e.g. a .map sourcemap) is
    # missing from STATIC_ROOT. The file is simply left unrewritten.
    manifest_strict = False
