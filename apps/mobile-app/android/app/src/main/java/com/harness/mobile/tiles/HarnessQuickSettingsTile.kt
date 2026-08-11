package com.harness.mobile.tiles

import android.content.Intent
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

class HarnessQuickSettingsTile : TileService() {
    override fun onStartListening() {
        qsTile?.label = "Harness"
        qsTile?.subtitle = "打开任务"
        qsTile?.state = Tile.STATE_INACTIVE
        qsTile?.updateTile()
    }

    override fun onClick() {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        launchIntent?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (launchIntent != null) {
            startActivityAndCollapse(launchIntent)
        }
    }
}
