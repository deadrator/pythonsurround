package com.deadrator.atmosconverter

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Equalizer
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.SpeakerGroup
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.deadrator.atmosconverter.dsp.SpeakerConfig
import com.deadrator.atmosconverter.ui.ConverterScreen
import com.deadrator.atmosconverter.ui.PlayerScreen
import com.deadrator.atmosconverter.ui.SpeakerShifterScreen
import com.deadrator.atmosconverter.ui.VisualizerScreen
import com.deadrator.atmosconverter.ui.theme.AtmosTheme
import com.deadrator.atmosconverter.ui.theme.Palette

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AtmosTheme {
                AtmosApp()
            }
        }
    }
}

enum class Tab(val route: String, val label: String, val icon: ImageVector) {
    Converter("converter", "Converter", Icons.Filled.GraphicEq),
    Shifter("shifter", "Speaker Shifter", Icons.Filled.SpeakerGroup),
    Player("player", "Player", Icons.Filled.MusicNote),
    Visualizer("visualizer", "Visualizer", Icons.Filled.Equalizer)
}

@Composable
fun AtmosApp() {
    val navController = rememberNavController()
    var currentTab by rememberSaveable { mutableStateOf(Tab.Converter.route) }

    // Shared across tabs (like the desktop app's single speaker_config):
    // the Converter's "Custom Speaker Layout" method uses what the
    // Speaker Shifter tab edits.
    var speakerLayout by rememberSaveable { mutableStateOf("5.1") }
    val speakerConfig = remember(speakerLayout) { SpeakerConfig(speakerLayout) }

    Scaffold(
        containerColor = Palette.Bg,
        bottomBar = {
            NavigationBar {
                Tab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = currentTab == tab.route,
                        onClick = {
                            currentTab = tab.route
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.startDestinationId) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) }
                    )
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Tab.Converter.route,
            modifier = Modifier.padding(padding)
        ) {
            composable(Tab.Converter.route) {
                ConverterScreen(speakerConfig = speakerConfig)
            }
            composable(Tab.Shifter.route) {
                SpeakerShifterScreen(
                    config = speakerConfig,
                    layout = speakerLayout,
                    onLayoutChange = { speakerLayout = it }
                )
            }
            composable(Tab.Player.route) { PlayerScreen() }
            composable(Tab.Visualizer.route) { VisualizerScreen() }
        }
    }
}
