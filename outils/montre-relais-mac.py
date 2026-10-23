# Relais local entre la montre Garmin (branchée en USB) et l'app « Mon Plan Sportif », version Mac.
# macOS ne sait pas lire une montre en MTP : ce petit serveur, lancé avec la session par installer-relais-mac.command,
# le fait via libmtp (Homebrew). Mêmes routes et mêmes réponses que montre-relais.ps1 (Windows) : l'app ne voit
# pas la différence.
#
# Routes (toutes protégées par le jeton, en-tête X-Relais-Jeton) :
#   GET  /status                       montre branchée ? nom de l'appareil
#   GET  /activities?days=30           sorties récentes de GARMIN/Activity (nom, taille, date)
#   GET  /activities/<nom>.fit         contenu d'une sortie
#   POST /workouts/<nom>.fit           dépose une séance dans GARMIN/NewFiles (prise en compte au débranchement)
#   GET  /workouts                     séances de l'app sur la montre (nom, dossier, date, empreinte du contenu)
#   POST /remove/<nom>.fit             retire une séance de l'app (déplacée, pas effacée)
#   POST /cleanup?before=AAAA-MM-JJ    retire les séances de l'app datées d'avant cette date (déplacées, pas effacées)
#
# --dossier-test <chemin> : utilise un dossier normal contenant GARMIN/... à la place de la montre (tests).
import argparse
import ctypes
import ctypes.util
import glob
import hmac
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# Version des routes : l'app demande de réinstaller le relais si elle est plus ancienne que celle attendue
VERSION = 2
DEFAULT_BASE = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'MonPlan')

parser = argparse.ArgumentParser()
parser.add_argument('--config', default=os.path.join(DEFAULT_BASE, 'relais.json'))
parser.add_argument('--dossier-test')
parser.add_argument('--jeton')
parser.add_argument('--origines', nargs='*', default=[])
parser.add_argument('--port', type=int, default=47812)
args = parser.parse_args()

BASE = os.path.join(args.dossier_test, '_relais') if args.dossier_test else DEFAULT_BASE
TEMP = os.path.join(tempfile.gettempdir(), 'monplan-relais')
RETIRES = os.path.join(BASE, 'retires')
LOG_FILE = os.path.join(BASE, 'relais.log')
for d in (BASE, TEMP, RETIRES):
    os.makedirs(d, exist_ok=True)

TOKEN, ORIGINS, PORT, LIBMTP_PATH = args.jeton, list(args.origines), args.port, None
if not TOKEN:
    with open(args.config, encoding='utf-8-sig') as f:
        cfg = json.load(f)
    TOKEN = cfg.get('token')
    ORIGINS = list(cfg.get('origins') or [])
    PORT = int(cfg.get('port') or PORT)
    LIBMTP_PATH = cfg.get('libmtp')
if not TOKEN or len(TOKEN) < 32:
    sys.exit('Jeton absent ou trop court : relance installer-relais-mac.command')


def write_log(text):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('{:%Y-%m-%d %H:%M:%S} {}\n'.format(datetime.now(), text))
    except OSError:
        pass


# Origines autorisées : celles de la configuration + l'app lancée en local (tests)
def test_origin(origin):
    if not origin:
        return True  # pas de navigateur (ex. curl) : seul le jeton protège
    if origin in ORIGINS:
        return True
    return re.match(r'^http://(localhost|127\.0\.0\.1)(:\d+)?$', origin, re.I) is not None


# Nom de fichier simple uniquement : ni chemin, ni « .. »
def test_file_name(name):
    return re.match(r'^\w[\w.-]*\.fit$', name, re.I) is not None and '..' not in name


class RelayError(Exception):
    pass


# ---------------------------------------------------------------------------
# libmtp (Homebrew), appelée directement : seuls les dossiers GARMIN utiles sont parcourus
# ---------------------------------------------------------------------------
class MtpFile(ctypes.Structure):
    pass


MtpFile._fields_ = [
    ('item_id', ctypes.c_uint32), ('parent_id', ctypes.c_uint32), ('storage_id', ctypes.c_uint32),
    ('filename', ctypes.c_void_p), ('filesize', ctypes.c_uint64), ('modificationdate', ctypes.c_long),
    ('filetype', ctypes.c_int), ('next', ctypes.POINTER(MtpFile)),
]


class MtpStorage(ctypes.Structure):
    pass


MtpStorage._fields_ = [
    ('id', ctypes.c_uint32), ('StorageType', ctypes.c_uint16), ('FilesystemType', ctypes.c_uint16),
    ('AccessCapability', ctypes.c_uint16), ('MaxCapacity', ctypes.c_uint64), ('FreeSpaceInBytes', ctypes.c_uint64),
    ('FreeSpaceInObjects', ctypes.c_uint64), ('StorageDescription', ctypes.c_char_p),
    ('VolumeIdentifier', ctypes.c_char_p), ('next', ctypes.POINTER(MtpStorage)), ('prev', ctypes.POINTER(MtpStorage)),
]


# Début de LIBMTP_mtpdevice_t : seul le pointeur vers les stockages sert
class MtpDevice(ctypes.Structure):
    _fields_ = [('object_bitsize', ctypes.c_uint8), ('params', ctypes.c_void_p), ('usbinfo', ctypes.c_void_p),
                ('storage', ctypes.POINTER(MtpStorage))]


FILES_AND_FOLDERS_ROOT = 0xFFFFFFFF
FILETYPE_FOLDER = 0
_mtp = None


def load_libmtp():
    global _mtp
    if _mtp:
        return _mtp
    candidates = [LIBMTP_PATH, '/opt/homebrew/lib/libmtp.dylib', '/usr/local/lib/libmtp.dylib', ctypes.util.find_library('mtp')]
    for path in candidates:
        if path and (os.path.exists(path) or not os.path.isabs(path)):
            try:
                lib = ctypes.CDLL(path)
                break
            except OSError:
                continue
    else:
        raise RelayError('libmtp introuvable : relance installer-relais-mac.command')
    lib.LIBMTP_Init.restype = None
    lib.LIBMTP_Detect_Raw_Devices.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int)]
    lib.LIBMTP_Get_First_Device.restype = ctypes.POINTER(MtpDevice)
    lib.LIBMTP_Release_Device.argtypes = [ctypes.POINTER(MtpDevice)]
    lib.LIBMTP_Get_Storage.argtypes = [ctypes.POINTER(MtpDevice), ctypes.c_int]
    for fn in ('LIBMTP_Get_Friendlyname', 'LIBMTP_Get_Modelname'):
        getattr(lib, fn).argtypes = [ctypes.POINTER(MtpDevice)]
        getattr(lib, fn).restype = ctypes.c_void_p
    lib.LIBMTP_Get_Files_And_Folders.argtypes = [ctypes.POINTER(MtpDevice), ctypes.c_uint32, ctypes.c_uint32]
    lib.LIBMTP_Get_Files_And_Folders.restype = ctypes.POINTER(MtpFile)
    lib.LIBMTP_destroy_file_t.argtypes = [ctypes.POINTER(MtpFile)]
    lib.LIBMTP_new_file_t.restype = ctypes.POINTER(MtpFile)
    lib.LIBMTP_Get_File_To_File.argtypes = [ctypes.POINTER(MtpDevice), ctypes.c_uint32, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.LIBMTP_Send_File_From_File.argtypes = [ctypes.POINTER(MtpDevice), ctypes.c_char_p, ctypes.POINTER(MtpFile), ctypes.c_void_p, ctypes.c_void_p]
    lib.LIBMTP_Delete_Object.argtypes = [ctypes.POINTER(MtpDevice), ctypes.c_uint32]
    lib.LIBMTP_Clear_Errorstack.argtypes = [ctypes.POINTER(MtpDevice)]
    lib.LIBMTP_Init()
    _mtp = lib
    return lib


_libc = ctypes.CDLL(ctypes.util.find_library('c')) if sys.platform != 'win32' else None
if _libc:
    _libc.free.argtypes = [ctypes.c_void_p]
    _libc.strdup.argtypes = [ctypes.c_char_p]
    _libc.strdup.restype = ctypes.c_void_p


def take_string(ptr):
    """Chaîne C allouée par libmtp : copiée puis libérée."""
    if not ptr:
        return None
    text = ctypes.string_at(ptr).decode('utf-8', 'replace')
    _libc.free(ptr)
    return text


def mtp_children(dev, storage_id, parent_id):
    """Contenu d'un dossier : liste de dict (id, name, size, mtime, folder)."""
    lib = load_libmtp()
    items = []
    node = lib.LIBMTP_Get_Files_And_Folders(dev, storage_id, parent_id)
    while node:
        f = node.contents
        items.append({
            'id': f.item_id, 'storage': f.storage_id, 'size': f.filesize, 'mtime': f.modificationdate,
            'name': ctypes.string_at(f.filename).decode('utf-8', 'replace') if f.filename else '',
            'folder': f.filetype == FILETYPE_FOLDER,
        })
        following = f.next
        lib.LIBMTP_destroy_file_t(node)
        node = following
    return items


def mtp_child_folder(dev, storage_id, parent_id, name):
    for item in mtp_children(dev, storage_id, parent_id):
        if item['folder'] and item['name'] == name:
            return item['id']
    return None


# ---------------------------------------------------------------------------
# Accès à la montre : MTP (libmtp), disque monté (/Volumes), ou dossier de test
# ---------------------------------------------------------------------------
class Watch:
    """kind = 'path' (garmin = chemin) ou 'mtp' (dev, storage, garmin = id du dossier GARMIN)."""

    def __init__(self, name, kind, garmin, dev=None, storage=None):
        self.name, self.kind, self.garmin, self.dev, self.storage = name, kind, garmin, dev, storage

    def close(self):
        if self.dev:
            load_libmtp().LIBMTP_Release_Device(self.dev)
            self.dev = None


def find_watch():
    if args.dossier_test:
        p = os.path.join(args.dossier_test, 'GARMIN')
        return Watch('Dossier de test', 'path', p) if os.path.isdir(p) else None
    # Montre en mode disque (ancien modèle) : GARMIN à la racine du volume
    for vol in sorted(glob.glob('/Volumes/*')):
        p = os.path.join(vol, 'GARMIN')
        if os.path.isdir(os.path.join(p, 'Activity')):
            return Watch(os.path.basename(vol), 'path', p)
    # Appareil MTP : GARMIN à la racine d'un stockage (« Internal Storage », « Primary »…)
    lib = load_libmtp()
    raw, count = ctypes.c_void_p(), ctypes.c_int(0)
    lib.LIBMTP_Detect_Raw_Devices(ctypes.byref(raw), ctypes.byref(count))
    if raw.value:
        _libc.free(raw)
    if count.value == 0:
        return None
    dev = lib.LIBMTP_Get_First_Device()
    if not dev:
        raise RelayError("Montre détectée mais occupée : ferme Garmin Express (et Transfert d'images), puis recommence.")
    lib.LIBMTP_Get_Storage(dev, 0)
    storage = dev.contents.storage
    while storage:
        s = storage.contents
        garmin = mtp_child_folder(dev, s.id, FILES_AND_FOLDERS_ROOT, 'GARMIN')
        if garmin:
            name = take_string(lib.LIBMTP_Get_Friendlyname(dev)) or take_string(lib.LIBMTP_Get_Modelname(dev)) or 'Montre Garmin'
            return Watch(name, 'mtp', garmin, dev, s.id)
        storage = s.next
    lib.LIBMTP_Release_Device(dev)
    return None


def name_date(name):
    """Sorties nommées AAAA-MM-JJ-HH-MM-SS.fit par la montre."""
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', name)
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups()))
    except ValueError:
        return None


def watch_files(watch, sub):
    """Fichiers .fit d'un sous-dossier de GARMIN : dict name, size, modified, path ou id."""
    files = []
    if watch.kind == 'path':
        folder = os.path.join(watch.garmin, sub)
        if not os.path.isdir(folder):
            return []
        for entry in os.scandir(folder):
            if entry.is_file() and entry.name.lower().endswith('.fit'):
                st = entry.stat()
                files.append({'name': entry.name, 'size': st.st_size, 'modified': datetime.fromtimestamp(st.st_mtime), 'path': entry.path})
        return files
    folder = mtp_child_folder(watch.dev, watch.storage, watch.garmin, sub)
    if not folder:
        return []
    for item in mtp_children(watch.dev, watch.storage, folder):
        if item['folder'] or not item['name'].lower().endswith('.fit'):
            continue
        modified = datetime.fromtimestamp(item['mtime']) if item['mtime'] > 0 else None
        if not modified or modified.year < 2000:
            modified = name_date(item['name'])
        files.append({'name': item['name'], 'size': item['size'], 'modified': modified, 'id': item['id']})
    return files


def read_watch_file(watch, file):
    if 'path' in file:
        with open(file['path'], 'rb') as f:
            return f.read()
    local = os.path.join(TEMP, file['name'])
    try:
        if load_libmtp().LIBMTP_Get_File_To_File(watch.dev, file['id'], local.encode('utf-8'), None, None) != 0:
            raise RelayError('Copie de {} depuis la montre impossible'.format(file['name']))
        with open(local, 'rb') as f:
            return f.read()
    finally:
        if os.path.exists(local):
            os.remove(local)  # copie temporaire : rien ne reste sur le Mac


def write_watch_workout(watch, name, data):
    if watch.kind == 'path':
        folder = os.path.join(watch.garmin, 'NewFiles')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
        return
    lib = load_libmtp()
    new_files = mtp_child_folder(watch.dev, watch.storage, watch.garmin, 'NewFiles')
    if not new_files:
        raise RelayError('Dossier GARMIN/NewFiles introuvable sur la montre')
    # Même nom déjà présent : remplacé (comme le « oui à tout » de Windows)
    for item in mtp_children(watch.dev, watch.storage, new_files):
        if not item['folder'] and item['name'].lower() == name.lower():
            lib.LIBMTP_Delete_Object(watch.dev, item['id'])
    local = os.path.join(TEMP, name)
    with open(local, 'wb') as f:
        f.write(data)
    meta = lib.LIBMTP_new_file_t()  # type « inconnu » par défaut ; libéré avec son nom par destroy_file_t
    try:
        meta.contents.filename = _libc.strdup(name.encode('utf-8'))
        meta.contents.filesize = len(data)
        meta.contents.parent_id = new_files
        meta.contents.storage_id = watch.storage
        if lib.LIBMTP_Send_File_From_File(watch.dev, local.encode('utf-8'), meta, None, None) != 0:
            lib.LIBMTP_Clear_Errorstack(watch.dev)
            raise RelayError("Écriture de {} sur la montre impossible".format(name))
    finally:
        lib.LIBMTP_destroy_file_t(meta)
        os.remove(local)


# ---------------------------------------------------------------------------
# Séances de l'app sur la montre
# ---------------------------------------------------------------------------
# Dans NewFiles, une séance garde le nom donné par l'app (« 2026-10-23_ven_seuil_48e22570.fit »). Au débranchement,
# la montre l'intègre dans Workouts sous un nom tiré du nom affiché, coupé (« 10-23_Ven_-_Seuil_Lactique_-_2x_workout.fit » ;
# « 26-12-29_Mar_-_… » fin décembre), avec un contenu identique à l'octet près
def app_workout_date(name):
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_', name)
    if m:
        return m.group(1)
    m = re.match(r'^(?:(\d{2})-)?(\d{2})-(\d{2})_(Lun|Mar|Mer|Jeu|Ven|Sam|Dim)_-_.*_workout\.fit$', name, re.I)
    if not m:
        return None
    month, day = int(m.group(2)), int(m.group(3))
    now = datetime.now()
    # Année absente : celle qui place la date au plus près d'aujourd'hui
    years = [2000 + int(m.group(1))] if m.group(1) else [now.year - 1, now.year, now.year + 1]
    best = None
    for year in years:
        try:
            date = datetime(year, month, day)
        except ValueError:
            continue
        if best is None or abs((now - date).total_seconds()) < abs((now - best).total_seconds()):
            best = date
    return best.strftime('%Y-%m-%d') if best else None


# Empreinte FNV-1a 32 bits du contenu (la même que l'app met dans le nom de ses fichiers)
def fnv1a(data):
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return '{:08x}'.format(h)


# Empreintes déjà calculées (le fichier n'a pas changé tant que dossier, nom, taille et date sont les mêmes)
HASH_CACHE = {}


def watch_file_hash(watch, sub, file):
    # Nom donné par l'app : l'empreinte y est déjà
    m = re.match(r'^\d{4}-\d{2}-\d{2}_.*_([0-9a-f]{8})\.fit$', file['name'], re.I)
    if m:
        return m.group(1).lower()
    key = '{}|{}|{}|{}'.format(sub, file['name'], file['size'], file['modified'])
    if key not in HASH_CACHE:
        HASH_CACHE[key] = fnv1a(read_watch_file(watch, file))
    return HASH_CACHE[key]


def app_workouts(watch):
    """Séances de l'app, dans Workouts et NewFiles : dict name, folder, date, file."""
    found = []
    for sub in ('Workouts', 'NewFiles'):
        for file in watch_files(watch, sub):
            date = app_workout_date(file['name'])
            if date:
                found.append({'name': file['name'], 'folder': sub, 'date': date, 'file': file})
    return found


# Déplace (sans effacer) vers ~/Library/Application Support/MonPlan/retires
def move_watch_file_away(watch, file):
    target = os.path.join(RETIRES, file['name'])
    if os.path.exists(target):
        os.remove(target)
    if 'path' in file:
        shutil.move(file['path'], target)
        return
    data = read_watch_file(watch, file)
    with open(target, 'wb') as f:
        f.write(data)
    if load_libmtp().LIBMTP_Delete_Object(watch.dev, file['id']) != 0:
        load_libmtp().LIBMTP_Clear_Errorstack(watch.dev)
        raise RelayError('Retrait de {} impossible'.format(file['name']))


# ---------------------------------------------------------------------------
# Serveur HTTP local
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, content_type='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        origin = self.headers.get('Origin')
        if origin and test_origin(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, code, value):
        self.send(code, json.dumps(value, ensure_ascii=False))

    def read_body(self, maximum):
        length = int(self.headers.get('Content-Length') or 0)
        if length > maximum:
            raise RelayError('Fichier trop gros')
        return self.rfile.read(length)

    def do_OPTIONS(self):
        self.handle_route()

    def do_GET(self):
        self.handle_route()

    def do_POST(self):
        self.handle_route()

    def handle_route(self):
        try:
            self.route()
        except Exception as e:  # noqa: BLE001 — toute erreur part au journal et à l'app
            write_log('Erreur : {}'.format(e))
            try:
                self.send_json(500, {'error': str(e)})
            except OSError:
                pass

    def route(self):
        origin = self.headers.get('Origin')
        if not test_origin(origin):
            return self.send_json(403, {'error': 'Origine non autorisée'})

        # Pré-contrôle CORS (+ accès au réseau local depuis un site public)
        if self.command == 'OPTIONS':
            self.send_response(204)
            if origin:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'X-Relais-Jeton, Content-Type')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Access-Control-Max-Age', '600')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if not hmac.compare_digest((self.headers.get('X-Relais-Jeton') or '').encode('utf-8'), TOKEN.encode('utf-8')):
            return self.send_json(401, {'error': 'Jeton refusé'})

        url = urlparse(self.path)
        path = unquote(url.path)
        query = parse_qs(url.query)

        try:
            watch = find_watch()
        except RelayError as e:
            if self.command == 'GET' and path == '/status':
                return self.send_json(200, {'relay': True, 'version': VERSION, 'watch': False, 'name': None, 'error': str(e)})
            return self.send_json(409, {'error': str(e)})
        try:
            self.watch_route(watch, path, query)
        finally:
            if watch:
                watch.close()

    def watch_route(self, watch, path, query):
        method = self.command
        if method == 'GET' and path == '/status':
            return self.send_json(200, {'relay': True, 'version': VERSION, 'watch': bool(watch), 'name': watch.name if watch else None})
        if not watch:
            return self.send_json(409, {'error': 'Montre non détectée'})

        if method == 'GET' and path == '/activities':
            days = 30
            if query.get('days'):
                days = min(365, max(1, int(query['days'][0])))
            since = datetime.now() - timedelta(days=days)
            recent = sorted((f for f in watch_files(watch, 'Activity') if f['modified'] and f['modified'] >= since),
                            key=lambda f: f['modified'])
            return self.send_json(200, [{'name': f['name'], 'size': f['size'], 'modified': f['modified'].strftime('%Y-%m-%dT%H:%M:%S')} for f in recent])

        m = re.match(r'^/activities/([^/]+)$', path)
        if method == 'GET' and m:
            name = m.group(1)
            if not test_file_name(name):
                return self.send_json(400, {'error': 'Nom de fichier invalide'})
            file = next((f for f in watch_files(watch, 'Activity') if f['name'].lower() == name.lower()), None)
            if not file:
                return self.send_json(404, {'error': 'Sortie introuvable'})
            return self.send(200, read_watch_file(watch, file), 'application/octet-stream')

        m = re.match(r'^/workouts/([^/]+)$', path)
        if method == 'POST' and m:
            name = m.group(1)
            if not test_file_name(name):
                return self.send_json(400, {'error': 'Nom de fichier invalide'})
            data = self.read_body(1024 * 1024)
            if len(data) < 14 or data[8:12] != b'.FIT':
                return self.send_json(400, {'error': "Ce n'est pas un fichier .FIT"})
            write_watch_workout(watch, name, data)
            write_log('Séance envoyée : {}'.format(name))
            return self.send_json(200, {'ok': True})

        # Séances de l'app présentes sur la montre, rangées (Workouts) ou en attente (NewFiles), avec l'empreinte
        # de leur contenu : l'app reconnaît ainsi une séance à jour même renommée par la montre
        if method == 'GET' and path == '/workouts':
            return self.send_json(200, [{'name': w['name'], 'folder': w['folder'], 'date': w['date'],
                                         'hash': watch_file_hash(watch, w['folder'], w['file'])} for w in app_workouts(watch)])

        # Retire une séance de l'app (réalisée, remplacée, déplacée ou supprimée du plan) : déplacée, pas effacée.
        # Seul un fichier reconnu comme séance de l'app, présent sous ce nom exact, peut l'être
        m = re.match(r'^/remove/([^/]+)$', path)
        if method == 'POST' and m:
            name = m.group(1)
            if re.search(r'[\\/:*?"<>|]|\.\.', name) or not app_workout_date(name):
                return self.send_json(400, {'error': "Seules les séances créées par l'app peuvent être retirées"})
            removed = []
            for w in app_workouts(watch):
                if w['name'].lower() == name.lower():
                    move_watch_file_away(watch, w['file'])
                    removed.append('{}/{}'.format(w['folder'], name))
                    write_log('Séance retirée (plus à jour) : {}/{}'.format(w['folder'], name))
            return self.send_json(200, {'removed': removed})

        if method == 'POST' and path == '/cleanup':
            before = (query.get('before') or [''])[0]
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', before):
                return self.send_json(400, {'error': 'Date invalide'})
            # Seulement les séances de l'app datées d'avant
            removed = []
            for w in app_workouts(watch):
                if w['date'] < before:
                    move_watch_file_away(watch, w['file'])
                    removed.append(w['name'])
                    write_log('Séance passée retirée : {}/{}'.format(w['folder'], w['name']))
            return self.send_json(200, {'removed': removed})

        return self.send_json(404, {'error': 'Route inconnue'})


try:
    server = HTTPServer(('127.0.0.1', PORT), Handler)
except OSError as e:
    write_log('Démarrage impossible sur le port {} (déjà lancé ?) : {}'.format(PORT, e))
    sys.exit(1)
write_log('Relais démarré sur le port {}{}'.format(PORT, ' (dossier de test {})'.format(args.dossier_test) if args.dossier_test else ''))
server.serve_forever()
