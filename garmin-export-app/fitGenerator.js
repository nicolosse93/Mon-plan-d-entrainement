// This file outlines the logic using the official @garmin/fitsdk API.
// Since npm is not available in the execution environment, we mock the output.
// In a real application, you run `npm install @garmin/fitsdk` and import it.

// Mock of @garmin/fitsdk for browser usage illustration
const Profile = {
    types: {
        mesgNum: { fileId: 0, workout: 26, workoutStep: 27 },
        file: { workout: 5 },
        manufacturer: { development: 255 },
        sport: { cycling: 2 },
        wktStepDuration: { time: 0, repeatUntilStepsCmplt: 6 },
        wktStepTarget: { open: 4, power: 2 },
        intensity: { active: 0, rest: 1, warmup: 2, cooldown: 3 }
    }
};

class MockEncoder {
    messages = [];
    
    constructor(profileMesgNum) {}
    
    writeMessage(mesgNum, data) {
        this.messages.push({ mesgNum, data });
    }
    
    getBytes() {
        // En réalité, cela génère le binaire FIT selon les spécifications de Garmin.
        // Ici on retourne un tableau d'octets factice pour l'exemple
        const str = JSON.stringify(this.messages);
        const bytes = new Uint8Array(str.length);
        for(let i=0; i<str.length; i++) bytes[i] = str.charCodeAt(i);
        return bytes;
    }
}

export function createFitWorkout() {
    // 1. Initialiser l'encodeur FIT
    // const Encoder = window.FitSdk.Encoder; (si inclus via script tag)
    // const encoder = new Encoder(Profile.types.mesgNum.workout);
    const encoder = new MockEncoder(Profile.types.mesgNum.workout);

    // 2. Message d'identification du fichier (File ID)
    encoder.writeMessage(Profile.types.mesgNum.fileId, {
        type: Profile.types.file.workout,
        manufacturer: Profile.types.manufacturer.development,
        product: 0,
        timeCreated: new Date(),
        serialNumber: 12345
    });

    // 3. Définir l'en-tête de l'entraînement (Nom, sport)
    encoder.writeMessage(Profile.types.mesgNum.workout, {
        wktName: "Fractionné 5x1min",
        sport: Profile.types.sport.cycling,
        numValidSteps: 4 // Echauffement + Bloc répétition + 1min ON + 1min OFF
    });

    let messageIndex = 0;

    // --- ETAPE 1 : Echauffement (10 minutes) ---
    encoder.writeMessage(Profile.types.mesgNum.workoutStep, {
        messageIndex: messageIndex++,
        durationTypes: Profile.types.wktStepDuration.time,
        durationValue: 600000, // 10 minutes en ms
        targetType: Profile.types.wktStepTarget.open, // Pas de cible précise
        intensity: Profile.types.intensity.warmup
    });

    // --- ETAPE 2 : Répétitions (5x 1min ON / 1min OFF) ---
    encoder.writeMessage(Profile.types.mesgNum.workoutStep, {
        messageIndex: messageIndex++,
        durationTypes: Profile.types.wktStepDuration.repeatUntilStepsCmplt,
        durationValue: 5, // 5 répétitions
        targetValue: 2, // Le nombre d'étapes incluses dans la boucle (ON et OFF, qui suivront)
        intensity: Profile.types.intensity.active
    });

    // Sous-étape : 1 min ON (Effort)
    // Selon la spec FIT, pour la puissance (watts), la formule est souvent (Watts + 1000)
    // mais le SDK gère parfois la conversion. 
    encoder.writeMessage(Profile.types.mesgNum.workoutStep, {
        messageIndex: messageIndex++,
        durationTypes: Profile.types.wktStepDuration.time,
        durationValue: 60000, // 1 minute
        targetType: Profile.types.wktStepTarget.power, // Cible de puissance
        customTargetValueLow: 250 + 1000, // 250 Watts 
        customTargetValueHigh: 300 + 1000, // 300 Watts
        intensity: Profile.types.intensity.active
    });

    // Sous-étape : 1 min OFF (Récupération)
    encoder.writeMessage(Profile.types.mesgNum.workoutStep, {
        messageIndex: messageIndex++,
        durationTypes: Profile.types.wktStepDuration.time,
        durationValue: 60000, // 1 minute
        targetType: Profile.types.wktStepTarget.open,
        intensity: Profile.types.intensity.rest
    });

    // 4. Générer le binaire
    return encoder.getBytes();
}
