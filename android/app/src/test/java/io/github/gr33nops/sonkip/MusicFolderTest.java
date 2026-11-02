package io.github.gr33nops.sonkip;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.json.JSONArray;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class MusicFolderTest {
    @Test public void downloadPollingCopiesOnlyWhenCompletionCountChanges() {
        assertTrue(DownloadService.shouldSyncFolder(-1,0));
        assertFalse(DownloadService.shouldSyncFolder(0,0));
        assertTrue(DownloadService.shouldSyncFolder(0,1));
        assertFalse(DownloadService.shouldSyncFolder(3,3));
    }
    @Test public void copyTracksWritesReadableAudioAndSkipsCompletedCopies() throws Exception {
        android.content.Context context=RuntimeEnvironment.getApplication();
        context.getSharedPreferences("music-folder",0).edit().clear().commit();
        java.io.File root=new java.io.File(context.getFilesDir(),"music/tracks");root.mkdirs();
        java.io.File audio=new java.io.File(root,"Artist - Song.webm");
        java.nio.file.Files.write(audio.toPath(),new byte[]{1,2,3,4});
        TestDocuments provider=new TestDocuments();
        android.content.pm.ProviderInfo info=new android.content.pm.ProviderInfo();info.authority="music-test";
        provider.attachInfo(context,info);
        org.robolectric.shadows.ShadowContentResolver.registerProviderInternal("music-test",provider);
        JSONArray tracks=new JSONArray("[{\"id\":\"song\",\"filename\":\"Artist - Song.webm\",\"extension\":\"webm\"}]");
        MusicFolder.copyTracks(context,android.net.Uri.parse("content://music-test/tree/root"),tracks);
        assertArrayEquals(new byte[]{1,2,3,4},java.nio.file.Files.readAllBytes(provider.output.toPath()));
        assertEquals("Artist - Song.webm",provider.name);
        java.util.List<org.robolectric.shadows.ShadowContentResolver.NotifiedUri> notified=
            org.robolectric.Shadows.shadowOf(context.getContentResolver()).getNotifiedUris();
        assertEquals(android.net.Uri.parse("content://music-test/document/song"),notified.get(notified.size()-1).uri);
        MusicFolder.copyTracks(context,android.net.Uri.parse("content://music-test/tree/root"),tracks);
        assertEquals(1,provider.created);
        assertTrue(audio.isFile());
    }
    public static class TestDocuments extends android.content.ContentProvider {
        java.io.File output;String name;int created;boolean available=true;boolean throwsOnMissing;
        public boolean onCreate(){return true;}
        public android.os.Bundle call(String method,String arg,android.os.Bundle extras){
            if(method.equals("android:deleteDocument")){if(output!=null)output.delete();return new android.os.Bundle();}
            if(method.equals("android:createDocument")) {
                name=extras.getString("_display_name");created++;
                try{output=java.io.File.createTempFile("song", ".webm",getContext().getCacheDir());}catch(Exception e){throw new RuntimeException(e);}
                android.os.Bundle result=new android.os.Bundle();result.putParcelable("uri",android.net.Uri.parse("content://music-test/document/song"));return result;
            }
            return new android.os.Bundle();
        }
        public android.os.ParcelFileDescriptor openFile(android.net.Uri uri,String mode)throws java.io.FileNotFoundException{return android.os.ParcelFileDescriptor.open(output,android.os.ParcelFileDescriptor.MODE_READ_WRITE);}
        public android.database.Cursor query(android.net.Uri u,String[] p,String s,String[] a,String order){
            if(!available)throw new SecurityException("Folder permission unavailable");
            android.database.MatrixCursor c=new android.database.MatrixCursor(p);
            if(u.getPath().endsWith("/children")){if(output!=null && output.exists())c.addRow(new Object[]{"song"});}
            else if(u.getPath().endsWith("/root"))c.addRow(new Object[]{"root"});
            else if(throwsOnMissing && (output==null || !output.exists()))throw new IllegalArgumentException("Missing file for document");
            else if(output!=null && output.exists())c.addRow(new Object[]{"song"});return c;
        }
        public String getType(android.net.Uri u){return "audio/webm";}
        public android.net.Uri insert(android.net.Uri u,android.content.ContentValues v){throw new UnsupportedOperationException();}
        public int delete(android.net.Uri u,String s,String[] a){return 0;}
        public int update(android.net.Uri u,android.content.ContentValues v,String s,String[] a){return 0;}
    }
    @Test public void removedFolderFileIsReconciledWithoutRecreatingIt() throws Exception {
        android.content.Context context=RuntimeEnvironment.getApplication();
        MusicFolder.prefs(context).edit().clear().commit();
        TestDocuments provider=new TestDocuments();
        android.content.pm.ProviderInfo info=new android.content.pm.ProviderInfo();info.authority="music-test";
        provider.attachInfo(context,info);
        org.robolectric.shadows.ShadowContentResolver.registerProviderInternal("music-test",provider);
        java.io.File root=new java.io.File(context.getFilesDir(),"music/tracks");root.mkdirs();
        java.nio.file.Files.write(new java.io.File(root,"Song.webm").toPath(),new byte[]{1,2,3});
        JSONArray tracks=new JSONArray("[{\"id\":\"saved\",\"filename\":\"Song.webm\",\"extension\":\"webm\"}]");
        android.net.Uri tree=android.net.Uri.parse("content://music-test/tree/root");
        MusicFolder.copyTracks(context,tree,tracks);provider.output.delete();provider.throwsOnMissing=true;
        JSONArray removed=MusicFolder.reconcileTracks(context,tree,tracks);
        assertEquals("saved",removed.getString(0));
        assertEquals(1,provider.created);
    }
    @Test public void removingSavedSongDeletesItsLinkedFolderDocument() throws Exception {
        android.content.Context context=RuntimeEnvironment.getApplication();
        MusicFolder.prefs(context).edit().clear().commit();
        TestDocuments provider=new TestDocuments();
        android.content.pm.ProviderInfo info=new android.content.pm.ProviderInfo();info.authority="music-test";
        provider.attachInfo(context,info);
        org.robolectric.shadows.ShadowContentResolver.registerProviderInternal("music-test",provider);
        java.io.File root=new java.io.File(context.getFilesDir(),"music/tracks");root.mkdirs();
        java.nio.file.Files.write(new java.io.File(root,"Song.webm").toPath(),new byte[]{1,2,3});
        JSONArray tracks=new JSONArray("[{\"id\":\"saved\",\"filename\":\"Song.webm\",\"extension\":\"webm\"}]");
        android.net.Uri tree=android.net.Uri.parse("content://music-test/tree/root");
        MusicFolder.copyTracks(context,tree,tracks);
        assertTrue(provider.output.exists());
        MusicFolder.reconcileTracks(context,tree,new JSONArray());
        assertFalse(provider.output.exists());
    }
    @Test public void unavailableFolderNeverMeansDeleteAllSavedSongs() throws Exception {
        android.content.Context context=RuntimeEnvironment.getApplication();
        MusicFolder.prefs(context).edit().clear().putString("content://music-test/tree/root|saved", "content://music-test/document/song").commit();
        TestDocuments provider=new TestDocuments();provider.available=false;
        android.content.pm.ProviderInfo info=new android.content.pm.ProviderInfo();info.authority="music-test";
        provider.attachInfo(context,info);
        org.robolectric.shadows.ShadowContentResolver.registerProviderInternal("music-test",provider);
        try {
            MusicFolder.reconcileTracks(context,android.net.Uri.parse("content://music-test/tree/root"),new JSONArray());
            fail("An unreadable folder must stop reconciliation");
        } catch(SecurityException | java.io.IOException expected) {}
        assertTrue(MusicFolder.prefs(context).contains("content://music-test/tree/root|saved"));
    }
    @Test public void folderCopiesUseAudioMimeTypes() throws Exception {
        Class<?> type=null;
        try {type=Class.forName("io.github.gr33nops.sonkip.MusicFolder");}catch(ClassNotFoundException ignored){}
        assertNotNull("Shared-folder export needs an audio file handler",type);
        java.lang.reflect.Method mime=type.getDeclaredMethod("mime",String.class);mime.setAccessible(true);
        assertEquals("audio/webm",mime.invoke(null,"webm"));
        assertEquals("audio/mp4",mime.invoke(null,"m4a"));
        assertEquals("audio/ogg",mime.invoke(null,"opus"));
    }
    @Test public void libraryOffersFolderSelectionEvenWhenEmpty() {
        String[] action={null};
        NativeUi ui=new NativeUi(RuntimeEnvironment.getApplication(),(a,v)->action[0]=a);
        ui.setTracks(new JSONArray());ui.showTab("library");
        android.view.View button=ui.findViewWithTag("music-folder");
        assertNotNull("Folder choice must be available before the first download",button);
        button.performClick();assertEquals("music-folder",action[0]);
    }
}
