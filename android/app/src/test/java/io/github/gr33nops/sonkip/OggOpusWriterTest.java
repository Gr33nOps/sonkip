package io.github.gr33nops.sonkip;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class OggOpusWriterTest {
    @Test public void opusPacketDurationsUseThePacketToc() throws Exception {
        assertEquals(960,OggOpusWriter.packetSamples(new byte[]{(byte)0xf8,0}));
        assertEquals(1920,OggOpusWriter.packetSamples(new byte[]{(byte)0xf9,0}));
        assertEquals(120,OggOpusWriter.packetSamples(new byte[]{(byte)0x80,0}));
    }
    @Test public void pagesHaveHeadersSequencingAndEndGranule() throws Exception {
        ByteArrayOutputStream output=new ByteArrayOutputStream();
        byte[] head=ByteBuffer.allocate(19).order(ByteOrder.LITTLE_ENDIAN)
            .put("OpusHead".getBytes("US-ASCII")).put((byte)1).put((byte)2).putShort((short)312)
            .putInt(48000).putShort((short)0).put((byte)0).array();
        OggOpusWriter writer=new OggOpusWriter(output,head,7);
        writer.packet(new byte[]{(byte)0xf8,0},false,-1);
        writer.packet(new byte[]{(byte)0xf8,0},true,1800);
        byte[] bytes=output.toByteArray();int offset=0,pages=0;
        while(offset<bytes.length) {
            assertEquals("OggS",new String(bytes,offset,4,"US-ASCII"));
            ByteBuffer page=ByteBuffer.wrap(bytes,offset,bytes.length-offset).slice().order(ByteOrder.LITTLE_ENDIAN);
            assertEquals(pages,page.getInt(18));
            int segments=bytes[offset+26]&255,size=27+segments;
            for(int i=0;i<segments;i++)size+=bytes[offset+27+i]&255;
            if(pages==0)assertEquals(2,bytes[offset+5]);
            if(pages==2){assertEquals(4,bytes[offset+5]);assertEquals(1800,page.getLong(6));assertEquals(2,segments);}
            offset+=size;pages++;
        }
        assertEquals(3,pages);
    }
}
