"""Zip, unzip and Properties for File manager (Will, November 4, 2026).

Alt+Z zips the tagged items, or the current one, into the current folder. Alt+U unzips each
tagged zip file, or the current one, into a new folder named after it. Alt+Enter lists an item's
properties; music files add their title, artist, album, genre, year, track and length.

Nothing here replaces a file that is already there. A zip is written to a hidden temporary file
first and renamed when it is complete, and a zip is unzipped into a temporary folder first, so a
failure never leaves half a file or half a folder behind.
"""
import os
import shutil
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath

ZIP_TYPE = '.zip'
MAX_UNZIPPED = 20 * 1024 ** 3          # a zip that would unpack to more than this is refused
MAX_RATIO = 1000                       # nor one that grows over 1000 times (a zip bomb)
MAX_MEMBERS = 100000
FOLDER_COUNT_LIMIT = 50000             # Properties stops counting a folder's contents here


# Names ------------------------------------------------------------------------------------
def free_name(folder, name):
    """name in folder, or 'name (1).zip' and so on when it is taken."""
    folder = Path(folder)
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while target.exists():
        target = folder / (stem + ' (' + str(number) + ')' + suffix)
        number += 1
    return target.name


def zip_name(paths, folder):
    """The suggested zip name: the item's own name for one item, else the folder's name."""
    paths = [Path(p) for p in paths]
    if len(paths) == 1:
        base = paths[0].name if paths[0].is_dir() else paths[0].stem
    else:
        base = Path(folder).name or 'Archive'
    base = base.strip(' .') or 'Archive'
    return free_name(folder, base + ZIP_TYPE)


def with_zip_type(name):
    name = name.strip()
    return name if name.lower().endswith(ZIP_TYPE) else name + ZIP_TYPE


# Zip --------------------------------------------------------------------------------------
def _entries(path):
    """(file path or None for an empty folder, name inside the zip) for one tagged item."""
    path = Path(path)
    top = path.name
    if not path.is_dir():
        yield path, top
        return
    found = False
    for folder, folders, files in os.walk(path, followlinks=False):
        folders[:] = sorted(d for d in folders if not Path(folder, d).is_symlink())
        relative = Path(folder).relative_to(path)
        base = PurePosixPath(top, *relative.parts)
        if not folders and not files:
            yield None, str(base) + '/'
        for name in sorted(files):
            file = Path(folder, name)
            if file.is_symlink():
                continue
            found = True
            yield file, str(base / name)
    if not found and not any(path.iterdir()):
        yield None, top + '/'


def make_zip(paths, target):
    """Zip paths into target, a new file. Returns how many files went in."""
    target = Path(target)
    if target.exists():
        raise ValueError('A file named ' + target.name + ' is already there. Nothing was replaced. Choose another name.')
    if not target.parent.is_dir():
        raise ValueError('Open a folder before zipping.')
    paths = [Path(p) for p in paths]
    for path in paths:
        if not path.exists():
            raise ValueError(path.name + ' moved or was removed. Refresh the folder and try again.')
    names = [p.name.casefold() for p in paths]
    clash = next((p.name for p in paths if names.count(p.name.casefold()) > 1), None)
    if clash:
        raise ValueError('Two tagged items are both named ' + clash + '. Rename one, then zip again.')
    partial = target.with_name('.' + target.name + '.partial')
    count = 0
    try:
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for path in paths:
                for file, name in _entries(path):
                    if file is None:
                        archive.writestr(zipfile.ZipInfo(name), b'')
                        continue
                    resolved = file.resolve()
                    if resolved in (target.resolve(), partial.resolve()):
                        continue   # never zip the zip into itself
                    archive.write(file, name)
                    count += 1
        if target.exists():
            raise ValueError('A file named ' + target.name + ' appeared while zipping. Nothing was replaced.')
        os.replace(partial, target)
    except PermissionError:
        raise ValueError('Windows did not allow a file to be read or the zip to be saved. Check the folder, then try again.')
    finally:
        try:
            partial.unlink()
        except OSError:
            pass
    return count


# Unzip ------------------------------------------------------------------------------------
def _safe_member(name):
    """The parts of a name inside a zip, or None when it would land outside the new folder."""
    name = name.replace('\\', '/')
    if name.startswith('/') or (len(name) > 1 and name[1] == ':'):
        return None
    parts = [p for p in name.split('/') if p not in ('', '.')]
    if not parts or any(p == '..' for p in parts):
        return None
    return parts


def unzip_file(path):
    """Unzip path into a new folder beside it, named after it. Returns (folder, item count)."""
    path = Path(path)
    if path.suffix.lower() != ZIP_TYPE:
        raise ValueError(path.name + ' is not a zip file.')
    if not path.is_file():
        raise ValueError(path.name + ' moved or was removed. Refresh the folder and try again.')
    folder = path.parent / free_name(path.parent, path.stem.strip(' .') or 'Unzipped')
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ValueError(path.name + ' is not a working zip file. It may be damaged or still downloading.')
    with archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError(path.name + ' holds too many items to unzip safely.')
        if any(m.flag_bits & 0x1 for m in members):
            raise ValueError(path.name + ' needs a password. Voice Companion cannot unzip it.')
        total = sum(m.file_size for m in members)
        packed = max(1, sum(m.compress_size for m in members))
        if total > MAX_UNZIPPED or total > packed * MAX_RATIO and total > 100 * 1024 ** 2:
            raise ValueError(path.name + ' would unpack to far more than its size. It was not unzipped, to keep your computer safe.')
        if shutil.disk_usage(path.parent).free < total + 50 * 1024 ** 2:
            raise ValueError('There is not enough free space to unzip ' + path.name + '.')
        work = path.parent / ('.' + folder.name + '.unzipping')
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()
        count = 0
        try:
            for member in members:
                parts = _safe_member(member.filename)
                if parts is None:
                    continue   # a name that points outside the folder is skipped
                if stat.S_ISLNK(member.external_attr >> 16):
                    continue   # links are never created
                target = work.joinpath(*parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, 'xb') as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                count += 1
            if folder.exists():
                folder = path.parent / free_name(path.parent, folder.name)
            os.replace(work, folder)
        except (zipfile.BadZipFile, EOFError, RuntimeError):
            raise ValueError(path.name + ' is damaged. It was not unzipped.')
        except FileExistsError:
            raise ValueError(path.name + ' lists the same file twice. It was not unzipped.')
        except PermissionError:
            raise ValueError('Windows did not allow the files to be saved here. Check the folder, then try again.')
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return folder, count


# Properties -------------------------------------------------------------------------------
def spoken_size(size):
    if size is None:
        return ''
    exact = format(size, ',') + (' byte' if size == 1 else ' bytes')
    for unit, power in (('GB', 3), ('MB', 2), ('KB', 1)):
        if size >= 1024 ** power:
            value = size / 1024 ** power
            return (format(value, '.1f').rstrip('0').rstrip('.') + ' ' + unit + ', ' + exact)
    return exact


def spoken_time(stamp):
    if stamp is None:
        return ''
    moment = time.localtime(stamp)
    hour = moment.tm_hour % 12 or 12
    return (time.strftime('%B ', moment) + str(moment.tm_mday) + time.strftime(', %Y, ', moment)
            + str(hour) + time.strftime(':%M ', moment) + ('AM' if moment.tm_hour < 12 else 'PM'))


def spoken_length(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = [(hours, 'hour'), (minutes, 'minute'), (seconds, 'second')]
    words = [str(n) + ' ' + unit + ('' if n == 1 else 's') for n, unit in parts if n]
    return ', '.join(words) or '0 seconds'


def folder_contents(path):
    """'12 files, 3 folders, 4.2 MB', counting at most FOLDER_COUNT_LIMIT items."""
    files = folders = size = seen = 0
    pending = [str(path)]
    limited = False
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    seen += 1
                    if seen > FOLDER_COUNT_LIMIT:
                        limited = True
                        pending.clear()
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            folders += 1
                            pending.append(entry.path)
                        else:
                            files += 1
                            size += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    text = (str(files) + (' file, ' if files == 1 else ' files, ') + str(folders) + (' folder' if folders == 1 else ' folders'))
    return ('More than ' if limited else '') + text, size


def properties(path, extended=None):
    """The lines of Properties, each 'Label: value', for arrowing through one at a time.
    extended: a function giving the Windows details of a file (music tags), or None."""
    path = Path(path)
    try:
        info = path.stat()
    except OSError:
        raise ValueError(path.name + ' moved or was removed. Refresh the folder and try again.')
    folder = path.is_dir()
    lines = [('Name', path.name or str(path))]
    if folder:
        lines.append(('Type', 'Folder'))
    else:
        kind = path.suffix[1:].upper()
        lines.append(('Type', kind + ' file' if kind else 'File'))
    details = []
    if extended is not None and not folder:
        try:
            details = [(label, value) for label, value in extended(str(path)) if str(value).strip()]
        except Exception:
            details = []   # Windows could not read the details; the basic ones still show
    lines.extend(details)
    if folder:
        contains, size = folder_contents(path)
        lines.append(('Contains', contains))
        lines.append(('Size', spoken_size(size)))
    else:
        lines.append(('Size', spoken_size(info.st_size)))
    lines.append(('Location', str(path.parent)))
    created = getattr(info, 'st_birthtime', None) or (info.st_ctime if os.name == 'nt' else None)
    if created:
        lines.append(('Created', spoken_time(created)))
    lines.append(('Modified', spoken_time(info.st_mtime)))
    lines.append(('Accessed', spoken_time(info.st_atime)))
    flags = []
    if not os.access(path, os.W_OK):
        flags.append('read-only')
    attributes = getattr(info, 'st_file_attributes', 0)
    if attributes & getattr(stat, 'FILE_ATTRIBUTE_HIDDEN', 2) or path.name.startswith('.') and os.name != 'nt':
        flags.append('hidden')
    lines.append(('Attributes', ', '.join(flags) if flags else 'none'))
    return [label + ': ' + str(value) for label, value in lines if str(value).strip()]


# Windows details (music tags) read through the Shell, as File Explorer shows them.
SHELL_DETAILS = (('Title', 'System.Title'), ('Artist', 'System.Music.Artist'), ('Album', 'System.Music.AlbumTitle'),
                 ('Album artist', 'System.Music.AlbumArtist'), ('Genre', 'System.Music.Genre'),
                 ('Year', 'System.Media.Year'), ('Track', 'System.Music.TrackNumber'),
                 ('Length', 'System.Media.Duration'), ('Bit rate', 'System.Audio.EncodingBitrate'),
                 ('Authors', 'System.Author'), ('Pages', 'System.Document.PageCount'))


def detail_text(label, value):
    """A Shell property value as words. Lists join with commas; lengths and bit rates read naturally."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ', '.join(str(v) for v in value if str(v).strip())
    if label == 'Length':
        try:
            return spoken_length(int(value) / 10_000_000)   # 100-nanosecond units
        except (TypeError, ValueError):
            return ''
    if label == 'Bit rate':
        try:
            return str(int(value) // 1000) + ' kbps'
        except (TypeError, ValueError):
            return ''
    if label in ('Year', 'Track', 'Pages'):
        try:
            return str(int(value)) if int(value) else ''
        except (TypeError, ValueError):
            return ''
    return str(value).strip()
