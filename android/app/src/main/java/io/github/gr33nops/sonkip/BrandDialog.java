package io.github.gr33nops.sonkip;

import android.app.AlertDialog;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;

/** Website typography and square controls, with Android's dialog behavior. */
final class BrandDialog extends AlertDialog.Builder {
    private final Typeface body, bold, mono;

    BrandDialog(Context context) {
        super(context);
        body = Typeface.createFromAsset(context.getAssets(), "fonts/manrope-500.ttf");
        bold = Typeface.createFromAsset(context.getAssets(), "fonts/manrope-700.ttf");
        mono = Typeface.createFromAsset(context.getAssets(), "fonts/dm-mono-400.ttf");
    }

    @Override public AlertDialog create() {
        AlertDialog dialog = super.create();
        View decor = dialog.getWindow().getDecorView();
        decor.addOnAttachStateChangeListener(new View.OnAttachStateChangeListener() {
            @Override public void onViewAttachedToWindow(View view) {
                view.post(() -> style(view));
            }
            @Override public void onViewDetachedFromWindow(View view) {}
        });
        return dialog;
    }

    @Override public AlertDialog show() {
        AlertDialog dialog = create();
        dialog.show();
        return dialog;
    }

    private void style(View view) {
        if (view instanceof android.widget.ListView) {
            android.widget.ListView list = (android.widget.ListView) view;
            list.setDivider(new android.graphics.drawable.ColorDrawable(0x33111111));
            list.setDividerHeight(1);
            list.setOnHierarchyChangeListener(new ViewGroup.OnHierarchyChangeListener() {
                @Override public void onChildViewAdded(View parent, View child) { style(child); }
                @Override public void onChildViewRemoved(View parent, View child) {}
            });
        }
        if (view instanceof TextView) {
            TextView text = (TextView) view;
            String resourceName = "";
            if (view.getId() != View.NO_ID) {
                try { resourceName = view.getResources().getResourceEntryName(view.getId()); }
                catch (android.content.res.Resources.NotFoundException ignored) { /* Generated view ID. */ }
            }
            text.setTypeface("alertTitle".equals(resourceName) ? bold : body);
            text.setTextColor(0xff111111);
            if (view instanceof android.widget.CheckedTextView) {
                text.setTextSize(15);
                text.setMaxLines(2);
                text.setEllipsize(android.text.TextUtils.TruncateAt.END);
                text.setMinHeight(dp(view, 56));
                text.setPaddingRelative(dp(view, 24), dp(view, 10), dp(view, 24), dp(view, 10));
            }
            if (view instanceof Button && !(view instanceof android.widget.CompoundButton)) {
                Button button = (Button) view;
                boolean primary = view.getId() == android.R.id.button1;
                button.setTypeface(mono);
                button.setAllCaps(false);
                button.setLetterSpacing(.02f);
                button.setTextSize(13);
                button.setMinHeight(dp(view, 48));
                button.setMinimumHeight(dp(view, 48));
                button.setPadding(dp(view, 14), 0, dp(view, 14), 0);
                button.setStateListAnimator(null);
                GradientDrawable surface = new GradientDrawable();
                surface.setColor(primary ? 0xff111111 : 0xfff3f0e8);
                surface.setStroke(dp(view, 1), 0xff111111);
                button.setBackgroundTintList(null);
                button.setBackground(new RippleDrawable(ColorStateList.valueOf(0x33777777), surface, null));
                button.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},
                        new int[]{0xff8a877e,primary ? 0xffe8ff00 : 0xff111111}));
                if (button.getLayoutParams() instanceof ViewGroup.MarginLayoutParams) {
                    ViewGroup.MarginLayoutParams params = (ViewGroup.MarginLayoutParams) button.getLayoutParams();
                    params.setMarginStart(dp(view, 6));
                    button.setLayoutParams(params);
                }
            }
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) style(group.getChildAt(i));
        }
    }

    private static int dp(View view, int value) {
        return Math.round(value * view.getResources().getDisplayMetrics().density);
    }
}
