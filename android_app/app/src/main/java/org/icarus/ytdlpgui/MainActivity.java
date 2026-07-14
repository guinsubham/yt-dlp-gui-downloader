package org.icarus.ytdlpgui;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(16, 19, 24);
    private static final int PANEL = Color.rgb(29, 35, 44);
    private static final int INPUT = Color.rgb(17, 24, 33);
    private static final int TEXT = Color.rgb(244, 247, 251);
    private static final int MUTED = Color.rgb(174, 184, 197);
    private static final int ACCENT = Color.rgb(226, 61, 61);
    private static final int TEAL = Color.rgb(42, 167, 162);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private EditText urlInput;
    private Spinner presetSpinner;
    private TextView statusText;
    private TextView progressText;
    private ProgressBar progressBar;
    private TextView logText;
    private Button downloadButton;
    private int progressLineStart = -1;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
    }

    private ScrollView buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(20), dp(20), dp(20));
        root.setBackgroundColor(BG);
        scroll.addView(root);

        TextView eyebrow = label("YOUTUBE DOWNLOADER", 12, TEAL, true);
        root.addView(eyebrow);

        TextView title = label("YT-DLP GUI Downloader", 25, TEXT, true);
        title.setPadding(0, dp(4), 0, dp(4));
        root.addView(title);

        statusText = label("Ready", 13, Color.rgb(57, 217, 138), true);
        root.addView(statusText);

        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(16), dp(16), dp(16), dp(16));
        panel.setBackgroundColor(PANEL);
        root.addView(panel, blockParams(dp(16)));

        panel.addView(label("Download Settings", 16, TEXT, true));

        panel.addView(sectionLabel("Video link"));
        urlInput = input("paste your link here");
        panel.addView(urlInput, inputParams());

        panel.addView(sectionLabel("Preset"));
        presetSpinner = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            new String[] {
                "4K best available / MP4 or MKV",
                "Best video + audio / MP4",
                "1080p MP4",
                "720p MP4",
                "480p MP4",
                "Audio only / M4A"
            }
        );
        presetSpinner.setAdapter(adapter);
        panel.addView(presetSpinner, inputParams());

        progressText = label("Waiting for a download", 12, MUTED, false);
        panel.addView(progressText);

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(1000);
        progressBar.setProgress(0);
        panel.addView(progressBar, blockParams(dp(10)));

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        panel.addView(row, blockParams(dp(12)));

        downloadButton = new Button(this);
        downloadButton.setText("↓ Download");
        downloadButton.setTextColor(Color.WHITE);
        downloadButton.setBackgroundResource(getResources().getIdentifier("button_accent", "drawable", getPackageName()));
        downloadButton.setOnClickListener(view -> startDownload());
        row.addView(downloadButton, new LinearLayout.LayoutParams(0, dp(48), 1));

        Button clearButton = new Button(this);
        clearButton.setText("✕ Clear Log");
        clearButton.setTextColor(TEXT);
        clearButton.setBackgroundResource(getResources().getIdentifier("button_quiet", "drawable", getPackageName()));
        clearButton.setOnClickListener(view -> {
            logText.setText("");
            progressLineStart = -1;
        });
        LinearLayout.LayoutParams clearParams = new LinearLayout.LayoutParams(0, dp(48), 1);
        clearParams.setMargins(dp(10), 0, 0, 0);
        row.addView(clearButton, clearParams);

        LinearLayout logPanel = new LinearLayout(this);
        logPanel.setOrientation(LinearLayout.VERTICAL);
        logPanel.setPadding(dp(16), dp(16), dp(16), dp(16));
        logPanel.setBackgroundColor(PANEL);
        root.addView(logPanel, blockParams(dp(16)));

        logPanel.addView(label("Activity", 16, TEXT, true));
        logText = label("", 13, Color.rgb(216, 222, 232), false);
        logText.setTypeface(android.graphics.Typeface.MONOSPACE);
        logText.setPadding(dp(12), dp(12), dp(12), dp(12));
        logText.setBackgroundColor(INPUT);
        logPanel.addView(logText, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(240)));

        return scroll;
    }

    private void startDownload() {
        String url = urlInput.getText().toString().trim();
        if (url.isEmpty()) {
            appendLog("Paste a YouTube link first.");
            return;
        }

        File folder = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if (folder == null) {
            folder = getFilesDir();
        }

        downloadButton.setEnabled(false);
        setStatus("Downloading");
        setProgress(0, "Starting 8 chunk lanes...");
        appendLog("Saving to: " + folder.getAbsolutePath());

        File finalFolder = folder;
        executor.execute(() -> {
            try {
                Python py = Python.getInstance();
                PyObject module = py.getModule("downloader");
                module.callAttr("download", url, finalFolder.getAbsolutePath(), presetSpinner.getSelectedItem().toString(), this);
                setStatus("Complete");
                setProgress(100, "Download complete");
                appendLog("Done.");
            } catch (Exception exc) {
                setStatus("Error");
                appendLog("Error: " + exc.getMessage());
            } finally {
                runOnUiThread(() -> downloadButton.setEnabled(true));
            }
        });
    }

    public void setStatus(String text) {
        runOnUiThread(() -> statusText.setText(text));
    }

    public void setProgress(double value, String text) {
        runOnUiThread(() -> {
            int scaled = (int) Math.max(0, Math.min(1000, value * 10));
            progressBar.setProgress(scaled);
            progressText.setText(text);
        });
    }

    public void appendLog(String text) {
        runOnUiThread(() -> {
            logText.append(text + "\n");
            progressLineStart = -1;
        });
    }

    public void replaceProgressLog(String text) {
        runOnUiThread(() -> {
            String current = logText.getText().toString();
            if (progressLineStart < 0 || progressLineStart > current.length()) {
                progressLineStart = current.length();
                logText.append(text + "\n");
                return;
            }

            int lineEnd = current.indexOf('\n', progressLineStart);
            if (lineEnd < 0) {
                lineEnd = current.length();
            }
            String next = current.substring(0, progressLineStart) + text + current.substring(lineEnd);
            logText.setText(next);
        });
    }

    private TextView label(String text, int sp, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(sp);
        view.setTextColor(color);
        if (bold) {
            view.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        }
        return view;
    }

    private TextView sectionLabel(String text) {
        TextView view = label(text, 12, MUTED, false);
        view.setPadding(0, dp(14), 0, dp(4));
        return view;
    }

    private EditText input(String hint) {
        EditText input = new EditText(this);
        input.setHint(hint);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);
        input.setBackgroundResource(getResources().getIdentifier("input_bg", "drawable", getPackageName()));
        input.setPadding(dp(12), 0, dp(12), 0);
        return input;
    }

    private LinearLayout.LayoutParams inputParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        params.setMargins(0, 0, 0, dp(4));
        return params;
    }

    private LinearLayout.LayoutParams blockParams(int topMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, topMargin, 0, 0);
        return params;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}
