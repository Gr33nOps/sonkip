package io.github.gr33nops.sonkip;

import android.app.*;
import android.content.*;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.Locale;

final class DownloadNotice {
    static Notification build(Context context, JSONArray jobs, boolean importing) {
        int saved=0, failed=0, transferring=0, processing=0;
        double progress=0, speed=0;
        for(int i=0;i<jobs.length();i++) {
            JSONObject job=jobs.optJSONObject(i); if(job==null)continue;
            String status=job.optString("status");
            if(status.equals("complete")){saved++;progress+=100;}
            else if(status.equals("error")){failed++;progress+=100;}
            else if(status.equals("downloading")) {
                transferring++;progress+=Math.max(0,Math.min(100,job.optDouble("percent",0)));
                speed+=Math.max(0,job.optDouble("speed",0));
            } else if(status.equals("processing")){processing++;progress+=100;}
        }
        int total=jobs.length(), percent=total==0?0:(int)(progress/total);
        boolean complete=total>0 && saved+failed==total && !importing;
        boolean measuring=transferring>0 || processing>0 || saved+failed>0;
        String phase=complete?"Finished":transferring>0?"Downloading":processing>0?"Saving audio":importing?"Reading playlist":"Preparing audio";
        String text=phase+(measuring?" · "+percent+"%":"")+" · "+saved+" saved"+(failed>0?" · "+failed+" failed":"");
        String detail=text+(total>0?"\n"+(total-saved-failed)+" remaining of "+total:"");
        if(speed>0)detail+=" · "+String.format(Locale.ROOT,"%.1f MB/s",speed/1048576);
        if(importing && transferring>0)detail+="\nAnother playlist is being matched.";
        Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(context,"downloads"):new Notification.Builder(context);
        return builder.setSmallIcon(R.drawable.ic_stat_music).setLargeIcon(NotificationBrand.artwork()).setColor(NotificationBrand.ORANGE)
            .setSubText("sonkip. · LOCAL ONLY").setContentTitle(complete?"Your downloads are ready":"Saving your music")
            .setContentText(text).setStyle(new Notification.BigTextStyle().bigText(detail))
            .setOnlyAlertOnce(true).setOngoing(!complete).setShowWhen(false)
            .setProgress(100,percent,!measuring).setCategory(Notification.CATEGORY_PROGRESS)
            .setContentIntent(PendingIntent.getActivity(context,0,new Intent(context,MainActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT)).build();
    }
}
