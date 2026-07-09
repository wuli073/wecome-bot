import assert from 'node:assert/strict'
import test from 'node:test'
import {
  PACKAGED_EXE_NAME,
  getDeterministicDirOutputDir,
  getDeterministicPackagedExePath,
  getElectronBuilderArgs,
} from '../scripts/package-win.mjs'

test('getDeterministicDirOutputDir returns a fixed win-dir output root', () => {
  const projectRoot = 'C:/repo/bot/apps/desktop-rpa-runtime'
  assert.equal(
    getDeterministicDirOutputDir(projectRoot),
    'C:\\repo\\bot\\apps\\desktop-rpa-runtime\\dist-phase2-official\\win-dir',
  )
})

test('getDeterministicPackagedExePath returns the stable win-unpacked executable path', () => {
  const projectRoot = 'C:/repo/bot/apps/desktop-rpa-runtime'
  assert.equal(
    getDeterministicPackagedExePath(projectRoot),
    `C:\\repo\\bot\\apps\\desktop-rpa-runtime\\dist-phase2-official\\win-dir\\win-unpacked\\${PACKAGED_EXE_NAME}`,
  )
})

test('getElectronBuilderArgs for dir mode never references timestamped output folders', () => {
  const args = getElectronBuilderArgs('dir', 'C:/repo/bot/apps/desktop-rpa-runtime')
  assert.deepEqual(args, [
    '--win',
    'dir',
    '--config.directories.output=C:\\repo\\bot\\apps\\desktop-rpa-runtime\\dist-phase2-official\\win-dir',
  ])
  assert.equal(args.join(' ').includes('T04-24-26'), false)
})
