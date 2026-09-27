package com.shopaccounting.pos

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.json.JSONObject

/**
 * تطبيق نقطة البيع على الجوال:
 * يتصل بجهاز المحل على نفس الشبكة (بدون إنترنت) ويعرض تطبيق الموظفين (/m) ولوحة المالك (/owner) والمتجر (/shop).
 * الميزة الأصلية: مسح الباركود بكاميرا الجوال مباشرة (حتى بدون https)، وربط الجهاز بمسح رمز QR من البرنامج.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private val prefs by lazy { getSharedPreferences("shop", Context.MODE_PRIVATE) }

    private val server: String get() = prefs.getString("server", "") ?: ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (server.isEmpty()) showSetup() else showWeb("/m")
    }

    // ------------------------------------------------------------------ الربط بجهاز المحل
    private fun showSetup() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 96, 48, 48)
            gravity = Gravity.CENTER_HORIZONTAL
        }
        val title = TextView(this).apply {
            text = "ربط التطبيق بجهاز المحل\nConnect to the shop computer"
            textSize = 20f
            gravity = Gravity.CENTER
        }
        val hint = TextView(this).apply {
            text = "في البرنامج: الإعدادات ← نقاط الولاء ولوحة المالك ← رمز ربط تطبيق الجوال.\n" +
                "The phone must be on the shop Wi-Fi."
            setPadding(0, 24, 0, 24)
            gravity = Gravity.CENTER
        }
        val input = EditText(this).apply {
            setText(server.ifEmpty { "http://192.168.1.10:8765" })
            setSingleLine()
        }
        val scan = Button(this).apply {
            text = "📷 مسح رمز الربط / Scan pairing QR"
            setOnClickListener { scanCode { value -> saveServer(value) } }
        }
        val ok = Button(this).apply {
            text = "اتصال / Connect"
            setOnClickListener { saveServer(input.text.toString()) }
        }
        box.addView(title); box.addView(hint); box.addView(scan); box.addView(input); box.addView(ok)
        setContentView(box)
    }

    private fun saveServer(raw: String) {
        var v = raw.trim().removeSuffix("/")
        if (v.isEmpty()) return
        if (!v.startsWith("http")) v = "http://$v"
        if (!Regex("^https?://[^/]+:\\d+").containsMatchIn(v) && !v.substringAfter("://").contains(":")) v = "$v:8765"
        v = Regex("^(https?://[^/]+)").find(v)?.value ?: v
        prefs.edit().putString("server", v).apply()
        showWeb("/m")
    }

    // ------------------------------------------------------------------ الواجهة
    @SuppressLint("SetJavaScriptEnabled")
    private fun showWeb(path: String) {
        if (!::web.isInitialized) {
            web = WebView(this)
            web.settings.javaScriptEnabled = true
            web.settings.domStorageEnabled = true
            web.addJavascriptInterface(Bridge(), "AndroidBridge")
            web.webChromeClient = WebChromeClient()
            web.webViewClient = object : WebViewClient() {
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (request.isForMainFrame) showOffline()
                }
            }
        }
        setContentView(web)
        web.loadUrl(server + path)
    }

    private fun showOffline() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 120, 48, 48)
            gravity = Gravity.CENTER_HORIZONTAL
            setBackgroundColor(Color.WHITE)
        }
        box.addView(TextView(this).apply {
            text = "تعذر الوصول إلى جهاز المحل\n$server\n\nتأكد أن البرنامج يعمل وأن الجوال على شبكة المحل.\n" +
                "Could not reach the shop computer."
            textSize = 17f
            gravity = Gravity.CENTER
        })
        box.addView(Button(this).apply { text = "إعادة المحاولة / Retry"; setOnClickListener { showWeb("/m") } })
        box.addView(Button(this).apply { text = "تغيير الجهاز / Change"; setOnClickListener { showSetup() } })
        setContentView(box)
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, "📦 الأسعار والجرد / Stock")
        menu.add(0, 2, 0, "📊 لوحة المالك / Owner")
        menu.add(0, 3, 0, "🛵 المتجر / Store")
        menu.add(0, 4, 0, "⚙ تغيير جهاز المحل / Change shop")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> showWeb("/m")
            2 -> showWeb("/owner")
            3 -> showWeb("/shop")
            4 -> AlertDialog.Builder(this)
                .setMessage("تغيير جهاز المحل المرتبط؟ / Change the linked shop computer?")
                .setPositiveButton("نعم / Yes") { _, _ -> showSetup() }
                .setNegativeButton("لا / No", null).show()
        }
        return true
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::web.isInitialized && web.visibility == View.VISIBLE && web.canGoBack()) web.goBack()
        else @Suppress("DEPRECATION") super.onBackPressed()
    }

    // ------------------------------------------------------------------ مسح الباركود الأصلي
    private fun scanCode(onResult: (String) -> Unit) {
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(
                Barcode.FORMAT_EAN_13, Barcode.FORMAT_EAN_8, Barcode.FORMAT_UPC_A, Barcode.FORMAT_UPC_E,
                Barcode.FORMAT_CODE_128, Barcode.FORMAT_CODE_39, Barcode.FORMAT_QR_CODE
            ).build()
        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { code -> code.rawValue?.let(onResult) }
            .addOnFailureListener { e -> Toast.makeText(this, e.message ?: "Scan failed", Toast.LENGTH_LONG).show() }
    }

    /** يستدعيها تطبيق الموظفين: AndroidBridge.scan() ثم تصل النتيجة إلى window.onNativeScan(code) */
    inner class Bridge {
        @JavascriptInterface
        fun scan() {
            runOnUiThread {
                scanCode { value ->
                    web.evaluateJavascript("window.onNativeScan && window.onNativeScan(${JSONObject.quote(value)})", null)
                }
            }
        }

        @JavascriptInterface
        fun isNative(): Boolean = true
    }
}
