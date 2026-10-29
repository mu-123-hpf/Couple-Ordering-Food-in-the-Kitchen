package com.example.lovekitchen;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.JsResult;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public final class MainActivity extends Activity {
    private static final String BASE_URL = "https://kitchen.example.com/";
    private static final String HOST = "kitchen.example.com";
    private static final int CHOOSE_FILE = 1001, SAVE_EXPORT = 1002;
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorPanel;
    private TextView errorText;
    private ValueCallback<Uri[]> uploadCallback;
    private byte[] exportBytes;

    private int dp(float n) { return (int)(n * getResources().getDisplayMetrics().density + .5f); }
    private boolean isInternal(Uri uri) {
        return uri != null && "https".equalsIgnoreCase(uri.getScheme()) && HOST.equalsIgnoreCase(uri.getHost())
            && uri.getUserInfo() == null && (uri.getPort() == -1 || uri.getPort() == 443);
    }
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        final LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(255,249,250));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets edges = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                view.setPadding(edges.left, edges.top, edges.right, edges.bottom);
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
        FrameLayout frame = new FrameLayout(this);
        root.addView(frame, new LinearLayout.LayoutParams(-1, 0, 1));
        web = new WebView(this);
        web.setBackgroundColor(Color.WHITE);
        frame.addView(web, new FrameLayout.LayoutParams(-1, -1));
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(28), dp(28), dp(28), dp(28));
        errorPanel.setBackgroundColor(Color.rgb(255,249,250));
        TextView heading = new TextView(this);
        heading.setText("情侣厨房"); heading.setTextSize(25); heading.setTypeface(null, Typeface.BOLD);
        heading.setTextColor(Color.rgb(60,45,53)); heading.setGravity(Gravity.CENTER);
        errorPanel.addView(heading);
        errorText = new TextView(this);
        errorText.setTextSize(15); errorText.setGravity(Gravity.CENTER); errorText.setPadding(0,dp(20),0,dp(20));
        errorPanel.addView(errorText);
        Button retry = new Button(this); retry.setText("重新连接厨房");
        retry.setOnClickListener(v -> { errorPanel.setVisibility(View.GONE); web.loadUrl(BASE_URL); });
        errorPanel.addView(retry);
        errorPanel.setVisibility(View.GONE);
        frame.addView(errorPanel, new FrameLayout.LayoutParams(-1,-1));
        setContentView(root);
        root.requestApplyInsets();
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // only chooser-selected content URIs, no file:// navigation
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                if (isInternal(req.getUrl())) return false;
                if (req.isForMainFrame() && req.hasGesture()) openExternal(req.getUrl());
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                progress.setVisibility(View.VISIBLE); errorPanel.setVisibility(View.GONE);
            }
            @Override public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE); CookieManager.getInstance().flush();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showError("暂时无法连接服务器，请检查网络后重试。\n" + BASE_URL);
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, android.webkit.WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 500) showError("服务器暂时不可用，请稍后重试。");
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel(); showError("安全证书校验失败，已停止连接。请检查设备时间或联系管理员，不会忽略证书错误。");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                if (!isInternal(Uri.parse(url))) { result.cancel(); return true; }
                new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("确定",(d,w)->result.confirm())
                    .setNegativeButton("取消",(d,w)->result.cancel()).setOnCancelListener(d->result.cancel()).show();
                return true;
            }
            @Override public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                if (!isInternal(Uri.parse(url))) { result.cancel(); return true; }
                new AlertDialog.Builder(MainActivity.this).setMessage(message).setPositiveButton("知道了",(d,w)->result.confirm())
                    .setOnCancelListener(d->result.cancel()).show(); return true;
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!isInternal(Uri.parse(view.getUrl()))) { callback.onReceiveValue(null); return true; }
                if (uploadCallback != null) uploadCallback.onReceiveValue(null);
                uploadCallback = callback;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE); pick.setType("image/jpeg");
                try { startActivityForResult(Intent.createChooser(pick,"选择菜谱图片（JPEG）"), CHOOSE_FILE); }
                catch (ActivityNotFoundException e) { uploadCallback.onReceiveValue(null); uploadCallback=null; Toast.makeText(MainActivity.this,"未找到文件选择器",Toast.LENGTH_LONG).show(); }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, size) -> {
            if (url.startsWith("blob:") && isInternal(Uri.parse(web.getUrl()))) exportBackup();
            else openExternal(Uri.parse(url));
        });
        if (saved == null || web.restoreState(saved) == null || !isInternal(Uri.parse(web.getUrl()))) web.loadUrl(BASE_URL);
    }
    private void showError(String text) {
        errorText.setText(text); errorPanel.setVisibility(View.VISIBLE); progress.setVisibility(View.GONE);
    }
    private void openExternal(Uri uri) {
        if (uri == null || !("https".equalsIgnoreCase(uri.getScheme()) || "http".equalsIgnoreCase(uri.getScheme()))) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
        catch (ActivityNotFoundException e) { Toast.makeText(this,"未找到浏览器",Toast.LENGTH_LONG).show(); }
    }
    private void exportBackup() {
        final String cookies = CookieManager.getInstance().getCookie(BASE_URL);
        new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                conn=(HttpURLConnection)new URL(BASE_URL+"api/export").openConnection();
                conn.setConnectTimeout(15000); conn.setReadTimeout(15000); conn.setInstanceFollowRedirects(false);
                if(cookies!=null)conn.setRequestProperty("Cookie",cookies);
                if(conn.getResponseCode()!=200)throw new java.io.IOException("请先登录再导出");
                ByteArrayOutputStream output=new ByteArrayOutputStream();
                try(InputStream input=conn.getInputStream()){
                    byte[] buf=new byte[8192]; int count;
                    while((count=input.read(buf))!=-1){output.write(buf,0,count);if(output.size()>10*1024*1024)throw new java.io.IOException("备份过大");}
                }
                exportBytes=output.toByteArray();
                runOnUiThread(() -> {
                    Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT); save.addCategory(Intent.CATEGORY_OPENABLE);
                    save.setType("application/json"); save.putExtra(Intent.EXTRA_TITLE,"couple-kitchen-backup.json");
                    try { startActivityForResult(save,SAVE_EXPORT); }
                    catch(ActivityNotFoundException e){exportBytes=null;Toast.makeText(this,"未找到保存文件界面",Toast.LENGTH_LONG).show();}
                });
            } catch(Exception e){runOnUiThread(()->Toast.makeText(this,"导出失败，请确认登录及网络后重试",Toast.LENGTH_LONG).show());}
            finally {if(conn!=null)conn.disconnect();}
        },"kitchen-export").start();
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==CHOOSE_FILE && uploadCallback!=null){
            Uri selected=result==RESULT_OK && data!=null?data.getData():null;
            uploadCallback.onReceiveValue(selected!=null?new Uri[]{selected}:null);uploadCallback=null;
        }
        if(request==SAVE_EXPORT){
            byte[] bytes=exportBytes;exportBytes=null;
            if(result==RESULT_OK && data!=null && data.getData()!=null && bytes!=null){
                try(OutputStream output=getContentResolver().openOutputStream(data.getData())){
                    if(output==null)throw new java.io.IOException("Cannot open output");output.write(bytes);
                    Toast.makeText(this,"厨房备份已保存",Toast.LENGTH_LONG).show();
                }catch(Exception e){Toast.makeText(this,"保存失败，请重试",Toast.LENGTH_LONG).show();}
            }
        }
    }
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);web.saveState(out);}
    @Override protected void onPause(){super.onPause();web.onPause();CookieManager.getInstance().flush();}
    @Override protected void onResume(){super.onResume();if(web!=null)web.onResume();}
    @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
    @Override protected void onDestroy(){
        if(uploadCallback!=null){uploadCallback.onReceiveValue(null);uploadCallback=null;}
        if(web!=null){((FrameLayout)web.getParent()).removeView(web);web.destroy();}super.onDestroy();
    }
}
