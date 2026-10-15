package io.github.gr33nops.sonkip;

import android.graphics.*;

final class NotificationBrand {
    static final int ORANGE = Color.rgb(255,80,0);
    private static Bitmap artwork;
    static Bitmap artwork() {
        if(artwork!=null)return artwork;
        artwork=Bitmap.createBitmap(192,192,Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(artwork); Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        canvas.drawColor(Color.rgb(244,241,232));
        paint.setColor(ORANGE);canvas.drawCircle(102,103,82,paint);
        paint.setColor(Color.rgb(20,20,18));canvas.drawCircle(94,91,80,paint);
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(1.5f);paint.setColor(Color.rgb(57,57,54));
        for(int r=40;r<78;r+=6)canvas.drawCircle(94,91,r,paint);
        paint.setStyle(Paint.Style.FILL);paint.setColor(Color.rgb(220,255,0));canvas.drawCircle(94,91,32,paint);
        paint.setColor(Color.BLACK);paint.setTypeface(Typeface.create("sans-serif",Typeface.BOLD));
        paint.setTextSize(27);paint.setTextAlign(Paint.Align.CENTER);canvas.drawText("SK",94,101,paint);
        return artwork;
    }
}
