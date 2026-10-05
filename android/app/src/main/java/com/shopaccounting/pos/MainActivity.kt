package com.shopaccounting.pos

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.Menu
import android.view.MenuItem
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import com.google.android.gms.common.moduleinstall.ModuleInstall
import com.google.android.gms.common.moduleinstall.ModuleInstallRequest
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.URL
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * تطبيق نقطة البيع على الجوال:
 * يتصل بجهاز المحل على نفس الشبكة (بدون إنترنت) ويعرض تطبيق الموظفين (/m) ولوحة المالك (/owner) والمتجر (/shop).
 * يفتح مباشرة: يبحث تلقائياً عن جهاز المحل على شبكة الواي فاي (أول مرة، وكلما تغيّر عنوانه)،
 * ويبقى الدخول محفوظاً. لا يطلب أي صلاحيات (الماسح من Google لا يحتاج صلاحية الكاميرا).
 */
class MainActivity : Activity() {

    private var web: WebView? = null
    private val prefs by lazy { getSharedPreferences("shop", Context.MODE_PRIVATE) }
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var searching = false

    private val server: String get() = prefs.getString("server", "") ?: ""
    private val shopName: String get() = prefs.getString("shop", "") ?: ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        CookieManager.getInstance().setAcceptCookie(true)   // يبقى الدخول محفوظاً بين مرات الفتح
        preinstallScanner()
        if (server.isEmpty()) discover(firstRun = true) else showWeb("/m")
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onDestroy() {
        web?.destroy()
        web = null
        super.onDestroy()
    }

    // ------------------------------------------------------------------ البحث التلقائي عن جهاز المحل
    private data class Shop(val url: String, val name: String)

    /** يجرّب العنوان المحفوظ أولاً، ثم يفحص شبكة الواي فاي (نفس الشبكة الفرعية) بحثاً عن البرنامج */
    private fun discover(firstRun: Boolean = false, path: String = "/m") {
        if (searching) return
        searching = true
        showMessage("🔎 جارٍ البحث عن جهاز المحل…\nLooking for the shop computer…", progress = true)
        Thread {
            val saved = server
            val direct = if (saved.isNotEmpty()) ping(saved, 1500) else null
            val found = if (direct != null) listOf(direct) else scanNetwork()
            main.post {
                searching = false
                if (isFinishing) return@post
                val preferred = found.firstOrNull { it.url == saved }
                    ?: found.firstOrNull { shopName.isNotEmpty() && it.name == shopName }
                when {
                    preferred != null -> connect(preferred, path)
                    found.size == 1 -> connect(found[0], path)
                    found.size > 1 -> chooseShop(found, path)
                    firstRun || saved.isEmpty() -> showSetup(notFound = true)
                    else -> showOffline()
                }
            }
        }.start()
    }

    private fun ping(base: String, timeoutMs: Int): Shop? = try {
        val conn = URL("$base/ping").openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs + 400
        conn.instanceFollowRedirects = false
        try {
            if (conn.responseCode != 200) null else {
                val body = conn.inputStream.bufferedReader().use { it.readText().take(4096) }
                val js = JSONObject(body)
                if (js.optBoolean("ok")) Shop(base, js.optString("shop", "")) else null
            }
        } finally {
            conn.disconnect()
        }
    } catch (e: Exception) {
        null
    }

    private fun localIPv4(): Inet4Address? = try {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val lp = cm.getLinkProperties(cm.activeNetwork)
        lp?.linkAddresses?.map { it.address }?.filterIsInstance<Inet4Address>()
            ?.firstOrNull { it.isSiteLocalAddress }
    } catch (e: Exception) {
        null
    }

    private fun scanNetwork(): List<Shop> {
        val ip = localIPv4() ?: return emptyList()
        val parts = ip.hostAddress?.split(".") ?: return emptyList()
        if (parts.size != 4) return emptyList()
        val prefix = parts.take(3).joinToString(".")
        val port = Regex(":(\\d+)$").find(server)?.groupValues?.get(1) ?: "8765"
        val ports = if (port == "8765") listOf("8765") else listOf(port, "8765")
        val found = Collections.synchronizedList(mutableListOf<Shop>())
        val pool = Executors.newFixedThreadPool(48)
        for (p in ports) for (i in 1..254) {
            if ("$prefix.$i" == ip.hostAddress) continue
            pool.execute { ping("http://$prefix.$i:$p", 450)?.let { found.add(it) } }
        }
        pool.shutdown()
        pool.awaitTermination(20, TimeUnit.SECONDS)
        pool.shutdownNow()
        return found.distinctBy { it.url }.sortedBy { it.url }
    }

    private fun connect(shop: Shop, path: String) {
        prefs.edit().putString("server", shop.url).putString("shop", shop.name).apply()
        showWeb(path)
    }

    private fun chooseShop(shops: List<Shop>, path: String) {
        val labels = shops.map { (if (it.name.isNotBlank()) it.name + "\n" else "") + it.url.removePrefix("http://") }
        AlertDialog.Builder(this)
            .setTitle("اختر جهاز المحل / Choose the shop computer")
            .setItems(labels.toTypedArray()) { _, i -> connect(shops[i], path) }
            .setCancelable(false)
            .show()
    }

    // ------------------------------------------------------------------ الربط اليدوي (احتياطي)
    private fun showSetup(notFound: Boolean = false) {
        val box = column(96)
        box.addView(TextView(this).apply {
            text = "ربط التطبيق بجهاز المحل\nConnect to the shop computer"
            textSize = 20f
            gravity = Gravity.CENTER
        })
        box.addView(TextView(this).apply {
            text = (if (notFound) "لم نجد جهاز المحل تلقائياً. تأكد أن البرنامج مفتوح على الكمبيوتر وأن الجوال على واي فاي المحل.\n" +
                "The shop computer was not found automatically.\n\n" else "") +
                "أو امسح رمز الربط من البرنامج: الإعدادات ← نقاط الولاء ولوحة المالك ← رمز ربط تطبيق الجوال.\n" +
                "Or scan the pairing QR from the program settings."
            setPadding(0, 24, 0, 24)
            gravity = Gravity.CENTER
        })
        box.addView(Button(this).apply {
            text = "🔎 البحث مرة أخرى / Search again"
            setOnClickListener { discover(firstRun = server.isEmpty()) }
        })
        box.addView(Button(this).apply {
            text = "📷 مسح رمز الربط / Scan pairing QR"
            setOnClickListener { scanCode { value -> saveServer(value) } }
        })
        val input = EditText(this).apply {
            setText(server.ifEmpty { "http://192.168.1.10:8765" })
            setSingleLine()
        }
        box.addView(input)
        box.addView(Button(this).apply {
            text = "اتصال / Connect"
            setOnClickListener { saveServer(input.text.toString()) }
        })
        setContentView(box)
    }

    private fun saveServer(raw: String) {
        var v = raw.trim().removeSuffix("/")
        if (v.isEmpty()) return
        if (!v.startsWith("http://") && !v.startsWith("https://")) v = "http://$v"
        v = Regex("^(https?://[^/?#]+)").find(v)?.value ?: return
        if (!v.substringAfter("://").contains(":")) v = "$v:8765"
        prefs.edit().putString("server", v).putString("shop", "").apply()
        showWeb("/m")
    }

    // ------------------------------------------------------------------ الواجهة
    @SuppressLint("SetJavaScriptEnabled")
    private fun webView(): WebView {
        web?.let { return it }
        val w = WebView(this)
        w.settings.javaScriptEnabled = true
        w.settings.domStorageEnabled = true
        w.settings.allowFileAccess = false          // لا وصول لملفات الجوال من الصفحات
        w.settings.allowContentAccess = false
        w.settings.setGeolocationEnabled(false)
        CookieManager.getInstance().setAcceptThirdPartyCookies(w, false)
        w.addJavascriptInterface(Bridge(), "AndroidBridge")
        w.webChromeClient = WebChromeClient()
        w.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (isShopUrl(url.toString())) return false
                // أي رابط خارجي (واتساب، خرائط، مواقع) يُفتح خارج التطبيق: لا تصل صفحات غريبة إلى جسر التطبيق
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, url))
                } catch (e: Exception) {
                }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    // تغيّر عنوان جهاز المحل (مثلاً بعد إعادة تشغيل الراوتر)؟ نبحث عنه تلقائياً
                    val path = request.url.encodedPath ?: "/m"
                    discover(path = if (path.isEmpty()) "/m" else path)
                }
            }
        }
        web = w
        return w
    }

    private fun isShopUrl(url: String): Boolean {
        val base = server
        return base.isNotEmpty() && (url == base || url.startsWith("$base/") || url.startsWith("$base?") ||
            url.startsWith("$base#"))
    }

    private fun showWeb(path: String) {
        val w = webView()
        setContentView(w)
        w.loadUrl(server + path)
    }

    private fun showOffline() {
        val box = column(120)
        box.addView(TextView(this).apply {
            text = "تعذر الوصول إلى جهاز المحل\n${shopName.ifBlank { server }}\n\n" +
                "تأكد أن البرنامج يعمل على الكمبيوتر وأن الجوال على واي فاي المحل.\n" +
                "Could not reach the shop computer."
            textSize = 17f
            gravity = Gravity.CENTER
        })
        box.addView(Button(this).apply { text = "إعادة المحاولة / Retry"; setOnClickListener { discover() } })
        box.addView(Button(this).apply { text = "تغيير الجهاز / Change"; setOnClickListener { showSetup() } })
        setContentView(box)
    }

    private fun showMessage(msg: String, progress: Boolean) {
        val box = column(160)
        if (progress) box.addView(ProgressBar(this).apply { isIndeterminate = true })
        box.addView(TextView(this).apply {
            text = msg
            textSize = 17f
            gravity = Gravity.CENTER
            setPadding(0, 32, 0, 0)
        })
        setContentView(box)
    }

    /** عمود بألوان سمة الجهاز (فاتح/مظلم تلقائياً) */
    private fun column(top: Int) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(48, top, 48, 48)
        gravity = Gravity.CENTER_HORIZONTAL
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, "📦 الأسعار والجرد / Stock")
        menu.add(0, 5, 0, "✨ اسأل محلك / Ask your shop")
        menu.add(0, 2, 0, "📊 لوحة المالك / Owner")
        menu.add(0, 3, 0, "🛵 المتجر / Store")
        menu.add(0, 4, 0, "⚙ تغيير جهاز المحل / Change shop")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (server.isEmpty() && item.itemId != 4) {
            discover(firstRun = true)
            return true
        }
        when (item.itemId) {
            1 -> showWeb("/m")
            5 -> showWeb("/m#ask")
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
        val w = web
        if (w != null && w.parent != null && w.canGoBack()) w.goBack()
        else @Suppress("DEPRECATION") super.onBackPressed()
    }

    // ------------------------------------------------------------------ مسح الباركود الأصلي
    private fun scannerOptions() = GmsBarcodeScannerOptions.Builder()
        .setBarcodeFormats(
            Barcode.FORMAT_EAN_13, Barcode.FORMAT_EAN_8, Barcode.FORMAT_UPC_A, Barcode.FORMAT_UPC_E,
            Barcode.FORMAT_CODE_128, Barcode.FORMAT_CODE_39, Barcode.FORMAT_QR_CODE
        ).build()

    /** تنزيل وحدة الماسح في الخلفية عند أول تشغيل، فلا ينتظر الموظف عند أول مسح */
    private fun preinstallScanner() {
        try {
            val request = ModuleInstallRequest.newBuilder()
                .addApi(GmsBarcodeScanning.getClient(this, scannerOptions()))
                .build()
            ModuleInstall.getClient(this).installModules(request)
        } catch (e: Exception) {
        }
    }

    private fun scanCode(onResult: (String) -> Unit) {
        GmsBarcodeScanning.getClient(this, scannerOptions()).startScan()
            .addOnSuccessListener { code -> code.rawValue?.let(onResult) }
            .addOnFailureListener { e -> Toast.makeText(this, e.message ?: "Scan failed", Toast.LENGTH_LONG).show() }
    }

    /** يستدعيها تطبيق الموظفين: AndroidBridge.scan() ثم تصل النتيجة إلى window.onNativeScan(code) */
    inner class Bridge {
        @JavascriptInterface
        fun scan() {
            runOnUiThread {
                val w = web ?: return@runOnUiThread
                if (!isShopUrl(w.url ?: "")) return@runOnUiThread   // صفحات جهاز المحل فقط
                scanCode { value ->
                    web?.evaluateJavascript("window.onNativeScan && window.onNativeScan(${JSONObject.quote(value)})", null)
                }
            }
        }

        @JavascriptInterface
        fun isNative(): Boolean = true
    }
}
