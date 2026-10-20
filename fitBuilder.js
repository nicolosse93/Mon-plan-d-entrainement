/**
 * Micro-Encodeur FIT simplifié, autonome, sans dépendance.
 * Permet de créer un binaire compatible Garmin .FIT pour un entraînement (Workout).
 */

const MesgNum = { fileId: 0, workout: 26, workoutStep: 27 };
const FileType = { workout: 5 };
const Manufacturer = { development: 255 };
const Sport = { generic: 0, running: 1, cycling: 2, training: 10, cross_country_skiing: 12 };
const SubSport = { generic: 0, strength_training: 20, skate_skiing: 42 };
const WktStepDuration = { time: 0, distance: 1, open: 5, repeatUntilStepsCmplt: 6 };
const WktStepTarget = { open: 4, heartRate: 1, power: 2, speed: 0 };
const Intensity = { active: 0, rest: 1, warmup: 2, cooldown: 3, recovery: 4 };

class FitEncoder {
    constructor() {
        this.records = [];
        this.localMessageTypes = {};
        this.nextLocalMessageType = 0;
    }

    addMessage(mesgNum, fields) {
        // Définition simplifiée des champs (pour workout et fileId)
        let definition = this._getDefinition(mesgNum);
        
        // 1. Definition Message
        if (!this.localMessageTypes[mesgNum]) {
            this.localMessageTypes[mesgNum] = this.nextLocalMessageType++;
            this._writeDefinition(this.localMessageTypes[mesgNum], mesgNum, definition);
        }
        
        // 2. Data Message
        this._writeData(this.localMessageTypes[mesgNum], definition, fields);
    }

    _getDefinition(mesgNum) {
        // Spécifications FIT simplifiées pour chaque message
        if (mesgNum === MesgNum.fileId) {
            return [
                { defNum: 0, size: 1, type: 0 },   // type
                { defNum: 1, size: 2, type: 132 }, // manufacturer
                { defNum: 2, size: 2, type: 132 }, // product
                { defNum: 3, size: 4, type: 140 }, // serialNumber
                { defNum: 4, size: 4, type: 134 }  // timeCreated
            ];
        } else if (mesgNum === MesgNum.workout) {
            return [
                { defNum: 8, size: 16, type: 7 },  // wktName (string up to 16 chars)
                { defNum: 4, size: 1, type: 0 },   // sport
                { defNum: 11, size: 1, type: 0 },  // subSport
                { defNum: 6, size: 2, type: 132 }  // numValidSteps
            ];
        } else if (mesgNum === MesgNum.workoutStep) {
            return [
                { defNum: 254, size: 2, type: 132 }, // messageIndex
                { defNum: 0, size: 16, type: 7 },  // wktStepName
                { defNum: 1, size: 1, type: 0 },   // durationType
                { defNum: 2, size: 4, type: 134 }, // durationValue
                { defNum: 3, size: 1, type: 0 },   // targetType
                { defNum: 4, size: 4, type: 134 }, // targetValue
                { defNum: 5, size: 1, type: 0 },   // intensity
                { defNum: 9, size: 4, type: 134 }, // customTargetLow
                { defNum: 10, size: 4, type: 134 } // customTargetHigh
            ];
        }
        return [];
    }

    _writeDefinition(localType, globalType, fields) {
        // Header de définition
        this.records.push(0x40 | localType); // Bit 6 = 1 (Definition)
        this.records.push(0); // Reserved
        this.records.push(0); // Architecture (Little Endian)
        this.records.push(globalType & 0xFF, (globalType >> 8) & 0xFF); // Global Mesg Num
        this.records.push(fields.length); // Fields count
        
        fields.forEach(f => {
            this.records.push(f.defNum);
            this.records.push(f.size);
            this.records.push(f.type);
        });
    }

    _writeData(localType, definition, data) {
        // Header de données
        this.records.push(localType); // Bit 6 = 0 (Data)
        
        definition.forEach(def => {
            let val = data[def.defNum] !== undefined ? data[def.defNum] : 
                      data[this._getFieldName(def.defNum)]; // Fallback
                      
            if (val === undefined || val === null) {
                // Ecrire des "invalid values" (0xFF)
                for(let i=0; i<def.size; i++) this.records.push(0xFF);
                return;
            }

            if (def.type === 7) { // String
                // Les chaînes FIT sont en UTF-8 : on retire accents et caractères non ASCII
                let str = String(val).normalize('NFD').replace(/[^\x20-\x7E]/g, '').substring(0, def.size - 1);
                for(let i=0; i<str.length; i++) this.records.push(str.charCodeAt(i));
                this.records.push(0); // Null terminator
                for(let i=str.length+1; i<def.size; i++) this.records.push(0x00);
            } else if (def.size === 1) {
                this.records.push(val & 0xFF);
            } else if (def.size === 2) {
                this.records.push(val & 0xFF, (val >> 8) & 0xFF);
            } else if (def.size === 4) {
                this.records.push(val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF);
            }
        });
    }

    _getFieldName(defNum) {
        // Simple mapping pour usage interne facile
        const map = {
            0: "type", 1: "manufacturer", 2: "product", 3: "serial", 4: "time",
            8: "name", 6: "steps"
        };
        return map[defNum] || "unknown";
    }

    static crc16(bytes, start = 0, end = bytes.length) {
        // CRC officiel du protocole FIT (algorithme par quartets du SDK Garmin)
        const table = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
                       0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400];
        let crc = 0;
        for (let i = start; i < end; i++) {
            const byte = bytes[i];
            let tmp = table[crc & 0xF];
            crc = (crc >> 4) & 0x0FFF;
            crc = crc ^ tmp ^ table[byte & 0xF];
            tmp = table[crc & 0xF];
            crc = (crc >> 4) & 0x0FFF;
            crc = crc ^ tmp ^ table[(byte >> 4) & 0xF];
        }
        return crc;
    }

    getBytes() {
        // Entête FIT de 14 octets : taille, protocole 2.0, profil 21.32, taille des données, ".FIT", CRC entête
        const header = [14, 32, 2132 & 0xFF, (2132 >> 8) & 0xFF, 0, 0, 0, 0, 46, 70, 73, 84, 0, 0];

        // Taille totale
        const dataSize = this.records.length;
        header[4] = dataSize & 0xFF;
        header[5] = (dataSize >> 8) & 0xFF;
        header[6] = (dataSize >> 16) & 0xFF;
        header[7] = (dataSize >> 24) & 0xFF;

        const headerCrc = FitEncoder.crc16(header, 0, 12);
        header[12] = headerCrc & 0xFF;
        header[13] = (headerCrc >> 8) & 0xFF;

        const fitFile = new Uint8Array(header.length + this.records.length + 2);
        fitFile.set(header, 0);
        fitFile.set(this.records, header.length);

        // CRC du fichier (entête + données), exigé par Garmin Connect
        const fileCrc = FitEncoder.crc16(fitFile, 0, fitFile.length - 2);
        fitFile[fitFile.length - 2] = fileCrc & 0xFF;
        fitFile[fitFile.length - 1] = (fileCrc >> 8) & 0xFF;

        return fitFile;
    }
}

export { FitEncoder, MesgNum, FileType, Manufacturer, Sport, SubSport, WktStepDuration, WktStepTarget, Intensity };