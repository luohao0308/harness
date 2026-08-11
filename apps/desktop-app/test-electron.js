import { app } from 'electron';

console.log('Electron app imported successfully');
console.log('App version:', app.getVersion());

app.whenReady().then(() => {
  console.log('App is ready');
  app.quit();
});
