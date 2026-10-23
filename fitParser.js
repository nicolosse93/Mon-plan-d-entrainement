// Lecteur FIT minimal, sans dépendance, pour les fichiers d'activité de la montre (complément de fitBuilder.js).
// Lit le résumé (session), les tours (lap), les mesures seconde par seconde (record), les zones de la montre
// et l'heure locale, puis calcule temps par zone de FC, charge (TRIMP), courbes réduites et tracé GPS.
// Accepte aussi les .zip de Garmin Connect (« Exporter le fichier d'origine »). Expose window.FitParser.
(function () {
    const FIT_EPOCH = 631065600; // 31/12/1989 00:00 UTC, origine des dates FIT
    const SEMICIRCLE = 180 / 2 ** 31;
    const MAX_POINTS = 1000;     // courbes enregistrées
    const MAX_TRACK = 600;       // points du tracé GPS enregistré

    // Type de base FIT (5 bits bas) -> taille, lecture, valeur invalide
    const BASE = {
        0: [1, 'u8', 0xFF], 1: [1, 's8', 0x7F], 2: [1, 'u8', 0xFF], 3: [2, 's16', 0x7FFF], 4: [2, 'u16', 0xFFFF],
        5: [4, 's32', 0x7FFFFFFF], 6: [4, 'u32', 0xFFFFFFFF], 8: [4, 'f32', null], 10: [1, 'u8', 0],
        11: [2, 'u16', 0], 12: [4, 'u32', 0], 13: [1, 'u8', 0xFF]
    };

    // Messages et champs lus : numéro -> [nom, échelle, décalage]
    const MESSAGES = {
        0: { 0: ['type', 1] },                                                   // file_id
        7: { 1: ['max_hr', 1], 2: ['threshold_hr', 1], 3: ['ftp', 1] },         // zones_target
        18: {                                                                     // session
            2: ['start_time', 1], 5: ['sport', 1], 6: ['sub_sport', 1], 7: ['elapsed', 1000], 8: ['timer', 1000],
            9: ['distance', 100], 11: ['calories', 1], 14: ['avg_speed', 1000], 124: ['enhanced_avg_speed', 1000],
            15: ['max_speed', 1000], 125: ['enhanced_max_speed', 1000], 16: ['avg_hr', 1], 17: ['max_hr', 1],
            18: ['avg_cadence', 1], 20: ['avg_power', 1], 22: ['ascent', 1], 24: ['training_effect', 10],
            137: ['anaerobic_effect', 10]
        },
        19: {                                                                     // lap
            2: ['start_time', 1], 7: ['elapsed', 1000], 8: ['timer', 1000], 9: ['distance', 100], 13: ['avg_speed', 1000],
            110: ['enhanced_avg_speed', 1000], 15: ['avg_hr', 1], 16: ['max_hr', 1], 19: ['avg_power', 1],
            21: ['ascent', 1], 71: ['wkt_step_index', 1]
        },
        20: {                                                                     // record
            0: ['lat', 1], 1: ['lon', 1], 2: ['alt', 5, 500], 78: ['ealt', 5, 500], 3: ['hr', 1], 4: ['cad', 1],
            5: ['dist', 100], 6: ['spd', 1000], 73: ['espd', 1000], 7: ['pwr', 1]
        },
        34: { 5: ['local_timestamp', 1] }                                       // activity
    };

    function readValue(view, offset, kind, little) {
        switch (kind) {
            case 'u8': return view.getUint8(offset);
            case 's8': return view.getInt8(offset);
            case 'u16': return view.getUint16(offset, little);
            case 's16': return view.getInt16(offset, little);
            case 'u32': return view.getUint32(offset, little);
            case 's32': return view.getInt32(offset, little);
            case 'f32': return view.getFloat32(offset, little);
        }
        return null;
    }

    // Décode un fichier .FIT -> { fileType, zones, sessions, laps, records, activity }
    function decode(buffer) {
        const view = new DataView(buffer);
        if (buffer.byteLength < 12) throw new Error('Fichier trop court pour être un .FIT');
        const headerSize = view.getUint8(0);
        const signature = String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11));
        if (signature !== '.FIT') throw new Error("Ce n'est pas un fichier .FIT");
        const end = Math.min(buffer.byteLength, headerSize + view.getUint32(4, true));

        const definitions = {};
        const out = { fileType: null, zones: {}, sessions: [], laps: [], records: [], activity: null };
        let lastTimestamp = null;
        let pos = headerSize;
        while (pos < end) {
            const header = view.getUint8(pos++);
            let local;
            let compressedTs = null;
            if (header & 0x80) {
                // En-tête « horodatage compressé » : 5 bits de secondes relatifs au dernier horodatage complet
                local = (header >> 5) & 0x03;
                if (lastTimestamp !== null) {
                    const offset = header & 0x1F;
                    let ts = lastTimestamp - (lastTimestamp % 32) + offset;
                    if (offset < lastTimestamp % 32) ts += 32;
                    compressedTs = lastTimestamp = ts;
                }
            } else {
                local = header & 0x0F;
                if (header & 0x40) {
                    // Définition : architecture, numéro global, champs (+ champs développeur)
                    const little = view.getUint8(pos + 1) === 0;
                    const global = view.getUint16(pos + 2, little);
                    const count = view.getUint8(pos + 4);
                    pos += 5;
                    const fields = [];
                    for (let i = 0; i < count; i++, pos += 3) {
                        fields.push({ num: view.getUint8(pos), size: view.getUint8(pos + 1), base: view.getUint8(pos + 2) & 0x1F });
                    }
                    let devSize = 0;
                    if (header & 0x20) {
                        const devCount = view.getUint8(pos++);
                        for (let i = 0; i < devCount; i++, pos += 3) devSize += view.getUint8(pos + 1);
                    }
                    definitions[local] = { little, global, fields, devSize };
                    continue;
                }
            }

            const def = definitions[local];
            if (!def) throw new Error('Fichier .FIT illisible (définition manquante)');
            const wanted = MESSAGES[def.global];
            const msg = {};
            for (const f of def.fields) {
                const base = BASE[f.base];
                if (base && f.size === base[0]) {
                    const spec = wanted && wanted[f.num];
                    if (spec || f.num === 253) {
                        const raw = readValue(view, pos, base[1], def.little);
                        if (raw !== base[2] && raw !== null && !Number.isNaN(raw)) {
                            if (f.num === 253) msg.timestamp = lastTimestamp = raw;
                            else msg[spec[0]] = raw / spec[1] - (spec[2] || 0);
                        }
                    }
                }
                pos += f.size;
            }
            pos += def.devSize;
            if (msg.timestamp === undefined && compressedTs !== null) msg.timestamp = compressedTs;

            if (def.global === 0 && msg.type !== undefined) out.fileType = msg.type;
            else if (def.global === 7) Object.assign(out.zones, msg);
            else if (def.global === 18) out.sessions.push(msg);
            else if (def.global === 19) out.laps.push(msg);
            else if (def.global === 20 && msg.timestamp !== undefined) out.records.push(msg);
            else if (def.global === 34) out.activity = msg;
        }
        return out;
    }

    // Sport FIT (+ sous-sport) -> types de séance de l'app, par ordre de préférence
    function appTypes(sport, subSport) {
        if (sport === 1) return ['Course'];
        if (sport === 2) return ['Vélo'];
        if (sport === 10 || (sport === 4 && subSport === 20)) return ['Renfo'];
        if (sport === 12) return subSport === 42 ? ['Ski de fond skate', 'Ski de fond classique'] : ['Ski de fond classique', 'Ski de fond skate'];
        if (sport === 41 || sport === 19) return ['Kayak'];
        return [];
    }

    // Zone de FC (1 à 5) : base FC seuil (85/90/95/100 %) ou FC max (60/70/80/90 %)
    function hrZone(hr, basis) {
        if (!hr || !basis) return null;
        const r = hr / basis.hr;
        const cuts = basis.type === 'threshold' ? [0.85, 0.90, 0.95, 1.0] : [0.6, 0.7, 0.8, 0.9];
        const i = cuts.findIndex(c => r < c);
        return i === -1 ? 5 : i + 1;
    }

    // Moyenne par paquets pour garder au plus `max` points (null si aucune valeur dans le paquet)
    function downsample(points, max, keys) {
        const size = Math.max(1, Math.ceil(points.length / max));
        const out = Object.fromEntries(keys.map(k => [k, []]));
        for (let i = 0; i < points.length; i += size) {
            const chunk = points.slice(i, i + size);
            keys.forEach(k => {
                const vals = chunk.map(p => p[k]).filter(v => v !== undefined && v !== null);
                out[k].push(vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length * 100) / 100 : null);
            });
        }
        // Courbe absente de ce fichier (pas de capteur) : non enregistrée
        keys.forEach(k => { if (k !== 't' && out[k].every(v => v === null)) delete out[k]; });
        return out;
    }

    // Activités d'un fichier (une par séance ; plusieurs pour un fichier multisport).
    // options.thresholdHr : FC seuil du profil, utilisée si la montre n'en fournit pas
    function parseActivities(buffer, options = {}) {
        const fit = decode(buffer);
        if (fit.fileType !== null && fit.fileType !== 4) {
            throw new Error(fit.fileType === 5 ? "C'est un fichier d'entraînement planifié, pas une activité réalisée" : "Ce .FIT n'est pas une activité");
        }
        if (fit.sessions.length === 0) throw new Error('Aucune activité trouvée dans ce fichier');
        // Décalage heure locale (fourni par la montre), sinon celui du navigateur
        const a = fit.activity;
        const fixedOffset = a && a.timestamp && a.local_timestamp ? a.local_timestamp - a.timestamp : null;

        return fit.sessions.filter(s => s.start_time).map(s => {
            const startMs = (s.start_time + FIT_EPOCH) * 1000;
            const offset = fixedOffset !== null ? fixedOffset : -new Date(startMs).getTimezoneOffset() * 60;
            const local = new Date(startMs + offset * 1000);
            const elapsed = s.elapsed || s.timer || 0;
            const inSession = t => t >= s.start_time && t < s.start_time + elapsed + 1;

            const records = fit.records.filter(r => inSession(r.timestamp)).map(r => ({
                t: r.timestamp - s.start_time,
                hr: r.hr, cad: r.cad, pwr: r.pwr, dist: r.dist,
                speed: r.espd ?? r.spd, alt: r.ealt ?? r.alt,
                lat: r.lat !== undefined ? r.lat * SEMICIRCLE : undefined,
                lon: r.lon !== undefined ? r.lon * SEMICIRCLE : undefined
            }));

            // Base des zones : FC seuil (montre, sinon profil), sinon FC max (montre, sinon max observé)
            const observedMax = Math.max(s.max_hr || 0, ...records.map(r => r.hr || 0));
            const thresholdHr = fit.zones.threshold_hr || options.thresholdHr;
            const maxHr = fit.zones.max_hr || observedMax;
            const basis = thresholdHr ? { type: 'threshold', hr: Math.round(thresholdHr) }
                : maxHr ? { type: 'max', hr: Math.round(maxHr) } : null;

            // Temps par zone (pauses de plus de 10 s ignorées) et charge TRIMP d'Edwards
            let timeInZones = null;
            let load = null;
            if (basis && records.some(r => r.hr)) {
                timeInZones = [0, 0, 0, 0, 0];
                for (let i = 0; i < records.length - 1; i++) {
                    const zone = hrZone(records[i].hr, basis);
                    if (zone) timeInZones[zone - 1] += Math.min(10, records[i + 1].t - records[i].t);
                }
                load = Math.round(timeInZones.reduce((sum, sec, i) => sum + sec / 60 * (i + 1), 0));
            }

            const gps = records.filter(r => r.lat !== undefined && r.lon !== undefined && Math.abs(r.lat) > 0.0001);
            const step = Math.max(1, Math.ceil(gps.length / MAX_TRACK));
            const track = gps.filter((_, i) => i % step === 0 || i === gps.length - 1)
                .map(r => [Math.round(r.lat * 1e5) / 1e5, Math.round(r.lon * 1e5) / 1e5]);

            const laps = fit.laps
                .filter(l => inSession(l.start_time))
                .map(l => ({
                    elapsed: l.elapsed || null, timer: l.timer || null, distance: l.distance || null,
                    avg_speed: l.enhanced_avg_speed || l.avg_speed || null, avg_hr: l.avg_hr || null,
                    max_hr: l.max_hr || null, avg_power: l.avg_power || null, ascent: l.ascent || null,
                    step_index: l.wkt_step_index ?? null
                }));
            return {
                types: appTypes(s.sport, s.sub_sport),
                fit_sport: s.sport ?? null,
                fit_sub_sport: s.sub_sport ?? null,
                start_time: new Date(startMs).toISOString(),
                start_date_local: local.toISOString().slice(0, 10),
                elapsed_time: Math.round(elapsed) || null,
                timer_time: s.timer ? Math.round(s.timer) : null,
                distance: s.distance || null,
                total_ascent: s.ascent || null,
                avg_heart_rate: s.avg_hr || null,
                max_heart_rate: s.max_hr || (observedMax || null),
                avg_speed: s.enhanced_avg_speed || s.avg_speed || null,
                max_speed: s.enhanced_max_speed || s.max_speed || null,
                avg_cadence: s.avg_cadence || null,
                avg_power: s.avg_power || null,
                calories: s.calories || null,
                training_effect: s.training_effect || null,
                anaerobic_effect: s.anaerobic_effect || null,
                time_in_zones: timeInZones,
                zone_basis: basis,
                load,
                load_estimated: false,
                streams: records.length ? downsample(records, MAX_POINTS, ['t', 'hr', 'speed', 'pwr', 'alt', 'cad']) : null,
                track: track.length > 1 ? track : null,
                laps
            };
        });
    }

    // Fichiers .fit contenus dans un .zip (lecture du répertoire central ; décompression native du navigateur)
    async function unzipFitFiles(buffer) {
        const view = new DataView(buffer);
        let eocd = -1;
        for (let i = buffer.byteLength - 22; i >= Math.max(0, buffer.byteLength - 65557); i--) {
            if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
        }
        if (eocd < 0) throw new Error('Archive .zip illisible');
        const count = view.getUint16(eocd + 10, true);
        let p = view.getUint32(eocd + 16, true);
        const files = [];
        for (let n = 0; n < count; n++) {
            if (view.getUint32(p, true) !== 0x02014b50) break;
            const method = view.getUint16(p + 10, true);
            const compSize = view.getUint32(p + 20, true);
            const nameLen = view.getUint16(p + 28, true);
            const extraLen = view.getUint16(p + 30, true);
            const commentLen = view.getUint16(p + 32, true);
            const localOffset = view.getUint32(p + 42, true);
            const name = new TextDecoder().decode(new Uint8Array(buffer, p + 46, nameLen));
            p += 46 + nameLen + extraLen + commentLen;
            if (!/\.fit$/i.test(name)) continue;

            const dataStart = localOffset + 30 + view.getUint16(localOffset + 26, true) + view.getUint16(localOffset + 28, true);
            const data = new Uint8Array(buffer, dataStart, compSize);
            if (method === 0) files.push({ name, buffer: data.slice().buffer });
            else if (method === 8) {
                const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
                files.push({ name, buffer: await new Response(stream).arrayBuffer() });
            }
        }
        return files;
    }

    window.FitParser = { parseActivities, unzipFitFiles, hrZone };
})();
