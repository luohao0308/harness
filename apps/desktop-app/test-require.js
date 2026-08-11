console.log('=== Testing require("electron") ===')
console.log('process.type:', process.type)
console.log('process.versions.electron:', process.versions.electron)

const electron = require('electron')
console.log('typeof electron:', typeof electron)
console.log('electron value:', electron)

if (typeof electron === 'object') {
  console.log('electron.app:', typeof electron.app)
  console.log('electron.BrowserWindow:', typeof electron.BrowserWindow)
} else {
  console.log('ERROR: electron is not an object, it is:', typeof electron)
}
