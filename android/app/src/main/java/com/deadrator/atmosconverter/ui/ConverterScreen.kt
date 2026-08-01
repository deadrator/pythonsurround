package com.deadrator.atmosconverter.ui

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.deadrator.atmosconverter.dsp.CodecRegistry
import com.deadrator.atmosconverter.dsp.FilterPresets
import com.deadrator.atmosconverter.dsp.SpeakerConfig
import com.deadrator.atmosconverter.engine.FfmpegEngine
import com.deadrator.atmosconverter.ui.theme.Panel
import com.deadrator.atmosconverter.ui.theme.Type
import kotlinx.coroutines.launch
import java.io.File

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ConverterScreen(speakerConfig: SpeakerConfig) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val engine = remember { FfmpegEngine(context) }

    var inputUri by remember { mutableStateOf<Uri?>(null) }
    var inputName by remember { mutableStateOf<String?>(null) }
    var method by remember { mutableStateOf(FilterPresets.Method.ENHANCED) }
    var preset by remember { mutableStateOf("Android Best") }
    var codec by remember { mutableStateOf("aac") }
    var container by remember { mutableStateOf("m4a") }
    var bitrate by remember { mutableStateOf("256k") }
    var sofaPath by remember { mutableStateOf<String?>(null) }
    var converting by remember { mutableStateOf(false) }
    var progress by remember { mutableStateOf(0) }
    var outputFile by remember { mutableStateOf<File?>(null) }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            inputUri = uri
            inputName = uri.lastPathSegment?.substringAfterLast('/')
        }
    }

    val sofaPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            val f = FfmpegEngine.copyToCache(context, uri, "custom.sofa")
            sofaPath = f.absolutePath
        }
    }

    val shareLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {}



    fun share() {
        val f = outputFile ?: return
        val uri: Uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            f
        )
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "audio/*"
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        shareLauncher.launch(Intent.createChooser(intent, "Share converted audio"))
    }

    // Convert - guards mirror the desktop app: only apply the -af filter for
    // multichannel input (or upmix methods), otherwise just re-encode.
    fun convert() {
        val input = inputUri ?: return
        val name = inputName ?: "track"
        scope.launch {
            converting = true
            progress = 0
            outputFile = null
            try {
                val cached = FfmpegEngine.copyToCache(context, input, name)
                val base = name.substringBeforeLast('.')
                val outName = engine.outputName(base, container)
                val out = File(context.cacheDir, "out_$outName")
                val meta = com.deadrator.atmosconverter.engine.AudioProbe.probe(cached)
                val channels = meta?.channels ?: 0
                val methodKey = method
                val applyFilter = channels > 2 || methodKey in FilterPresets.UPMIX_METHODS
                val filter = engine.filterChainFor(methodKey, speakerConfig, sofaPath)
                val encodeArgs = CodecRegistry.encodeArgs(codec, bitrate.takeIf { it.isNotBlank() }, 48000)
                val outArgs = CodecRegistry.outputArgs(container)

                val ok = if (methodKey in FilterPresets.PASSTHROUGH_METHODS) {
                    engine.execute(
                        listOf("-i", cached.absolutePath, "-c:a", "copy", "-map_metadata", "0") +
                            outArgs + listOf("-y", out.absolutePath)
                    ) { p -> progress = p }
                } else if (applyFilter) {
                    engine.execute(
                        listOf("-i", cached.absolutePath, "-af", filter ?: FilterPresets.ENHANCED) +
                            encodeArgs + outArgs + listOf("-y", out.absolutePath)
                    ) { p -> progress = p }
                } else {
                    engine.execute(
                        listOf("-i", cached.absolutePath) + encodeArgs + outArgs + listOf("-y", out.absolutePath)
                    ) { p -> progress = p }
                }

                if (ok) {
                    val saved = FfmpegEngine.saveOutput(context, out, outName)
                    outputFile = saved
                    Toast.makeText(context, "✓ Saved: $outName", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(context, "✗ Conversion failed", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(context, "✗ ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                converting = false
            }
        }
    }

    // Wire preset -> codec/container/bitrate
    LaunchedEffect(preset) {
        CodecRegistry.PRESETS[preset]?.let { (c, cont, br) ->
            codec = c; container = cont; bitrate = br ?: ""
        }
    }

    // Wire method -> auto-switch to Custom when speaker layout is edited (live preview parity)
    fun onMethodChanged(newMethod: String) {
        method = newMethod
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("CONVERSION", style = Type.Eyebrow)
        Text("Surround to Binaural", style = Type.Title)
        Text(
            "Convert surround sound to stereo for TWS earbuds and headphones.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Panel {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { picker.launch(arrayOf("audio/*", "video/*", "*/*")) },
                       enabled = !converting) {
                    Text("Select Audio File")
                }
                inputName?.let {
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                } ?: Text(
                    "M4A / MP4 / MKV / AC3 / E-AC-3 / AC-4 / TrueHD / DTS / FLAC / WAV / OGG…",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        // Method
        Panel {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Method", style = MaterialTheme.typography.titleSmall)
                val methods = listOf(
                    "Standard Downmix" to FilterPresets.Method.STANDARD,
                    "Enhanced (Bass Boost)" to FilterPresets.Method.ENHANCED,
                    "Spatial Binaural" to FilterPresets.Method.SPATIAL,
                    "HRTF (SOFA)" to FilterPresets.Method.HRTF,
                    "Custom Speaker Layout" to FilterPresets.Method.CUSTOM,
                    "Surround Upmix to 5.1" to FilterPresets.Method.UPMIX51,
                    "Surround Upmix to 7.1" to FilterPresets.Method.UPMIX71,
                    "Downmix 7.1 to 5.1" to FilterPresets.Method.DOWNMIX51,
                    "Passthrough (Stream Copy)" to FilterPresets.Method.PASSTHROUGH
                )
                methods.forEach { (label, key) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(
                            selected = method == key,
                            onClick = { onMethodChanged(key) }
                        )
                        Text(label, modifier = Modifier.padding(start = 8.dp))
                    }
                }
                if (method == FilterPresets.Method.HRTF) {
                    OutlinedButton(onClick = { sofaPicker.launch(arrayOf("application/octet-stream", "*/*")) },
                                   enabled = !converting) {
                        Text(if (sofaPath != null) "SOFA selected ✓" else "Select SOFA file")
                    }
                }
                if (method == FilterPresets.Method.CUSTOM) {
                    Text(
                        "Speaker positions are set in the 🎧 Speaker Shifter tab",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }

        // Preset
        Panel {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Preset", style = MaterialTheme.typography.titleSmall)
                val presetNames = CodecRegistry.PRESETS.keys.toList()
                FlowRow {
                    presetNames.forEach { p ->
                        FilterChip(
                            selected = preset == p,
                            onClick = { preset = p },
                            label = { Text(p) },
                            modifier = Modifier.padding(end = 4.dp, bottom = 4.dp)
                        )
                    }
                }
            }
        }

        // Codec / container
        Panel {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Codec & Container", style = MaterialTheme.typography.titleSmall)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Codec:")
                    CodecDropdown(codec) { codec = it }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Container:")
                    ContainerDropdown(container) { container = it }
                }
                if (codec in setOf("aac", "mp3", "opus", "ac3", "eac3", "ac4", "dts")) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Bitrate:")
                        BitrateDropdown(bitrate) { bitrate = it }
                    }
                }
            }
        }

        // Progress
        if (converting) {
            LinearProgressIndicator(progress = { progress / 100f }, modifier = Modifier.fillMaxWidth())
            Text("Converting… $progress%", style = MaterialTheme.typography.bodySmall)
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { convert() }, enabled = !converting && inputUri != null) {
                Text("Convert")
            }
            if (outputFile != null) {
                OutlinedButton(onClick = { share() }) {
                    Icon(Icons.Filled.Share, contentDescription = null)
                    Text("Share")
                }
            }
        }
    }
}

@Composable
private fun CodecDropdown(codec: String, onChange: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) {
            Text(CodecRegistry.getCodec(codec)?.name ?: codec)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            CodecRegistry.CODECS.values.forEach { c ->
                DropdownMenuItem(text = { Text(c.name) }, onClick = {
                    onChange(c.name.lowercase()); expanded = false
                })
            }
        }
    }
}

@Composable
private fun ContainerDropdown(container: String, onChange: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) {
            Text(CodecRegistry.getContainer(container)?.name ?: container)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            CodecRegistry.CONTAINERS.values.forEach { c ->
                DropdownMenuItem(text = { Text(c.name) }, onClick = {
                    onChange(c.name.lowercase()); expanded = false
                })
            }
        }
    }
}

@Composable
private fun BitrateDropdown(bitrate: String, onChange: (String) -> Unit) {
    val options = listOf("96k", "128k", "192k", "256k", "320k", "384k", "512k", "768k")
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }) {
            Text(bitrate.ifBlank { "auto" })
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { b ->
                DropdownMenuItem(text = { Text(b) }, onClick = { onChange(b); expanded = false })
            }
        }
    }
}


