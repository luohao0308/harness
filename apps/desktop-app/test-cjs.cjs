const electron = require('electron');

console.log('Electron module:', electron);
console.log('Electron type:', typeof electron);
console.log('Electron keys:', Object.keys(electron || {}).slice(0, 20));
