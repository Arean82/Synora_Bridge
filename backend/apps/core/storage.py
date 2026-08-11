"""
Lenient static storage — tolerates bundled JS that references sourcemaps
which don't ship with the package (admin-material's bootstrap bundle does).

Django's HashedFilesMixin rewrites every `//# sourceMappingURL=x.map`
reference by hashing the referenced file; when that .map is absent it raises
MissingFileError (a ValueError subclass) and aborts the whole collectstatic
pass. The canonical fix: override `hashed_name` so a missing referenced file
keeps its original reference instead of raising. Real assets are still hashed
+ compressed as usual.
"""
import logging

from whitenoise.storage import CompressedManifestStaticFilesStorage

logger = logging.getLogger(__name__)


class LenientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            # Referenced file doesn't exist (e.g. a sourcemap that wasn't
            # shipped with the theme package) — keep the original reference.
            logger.warning("Static reference '%s' not found; keeping original.", name)
            return name
