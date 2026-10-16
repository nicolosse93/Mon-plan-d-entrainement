// Note: In a real project you'd use a bundler (Vite, Webpack, Parcel) 
// to bundle the @garmin/fitsdk for the browser.
// Since we don't have Node/NPM in this environment, we are writing the logic conceptually.
// In practice, you would import the Encoder from '@garmin/fitsdk'

import { createFitWorkout } from './fitGenerator.js';

document.getElementById('export-garmin-btn').addEventListener('click', () => {
    try {
        // 1. Générer le fichier FIT sous forme de Uint8Array
        const fitBytes = createFitWorkout();
        
        // 2. Créer un Blob à partir des données
        const fitBlob = new Blob([fitBytes], { type: "application/vnd.ant.fit" });
        
        // 3. Créer une URL temporaire pour le téléchargement
        const url = URL.createObjectURL(fitBlob);
        
        // 4. Créer un lien caché et déclencher le clic
        const a = document.createElement('a');
        a.href = url;
        a.download = 'fractionne_5x1min.fit';
        document.body.appendChild(a);
        a.click();
        
        // 5. Nettoyer
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        alert("Fichier téléchargé ! Vous pouvez maintenant l'importer sur Garmin Connect Web.");
    } catch (error) {
        console.error(error);
        alert("Erreur lors de la génération du fichier FIT : " + error.message);
    }
});
