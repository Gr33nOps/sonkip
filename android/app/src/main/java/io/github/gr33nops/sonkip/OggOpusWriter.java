package io.github.gr33nops.sonkip;

import java.io.IOException;
import java.io.OutputStream;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/** RFC 7845 Ogg framing for existing Opus packets; no audio is re-encoded. */
final class OggOpusWriter {
    private final OutputStream output;
    private final int serial;
    private int sequence;
    private long samples;
    private final ByteArrayOutputStream packets=new ByteArrayOutputStream();
    private final ByteArrayOutputStream lacing=new ByteArrayOutputStream();
    private int pageSamples;

    OggOpusWriter(OutputStream output, byte[] head, int serial) throws IOException {
        if(head.length<19 || !new String(head,0,8,StandardCharsets.US_ASCII).equals("OpusHead"))
            throw new IOException("Missing Opus codec header");
        this.output=output;this.serial=serial;
        page(head,2,0);
        byte[] vendor="Sonkip".getBytes(StandardCharsets.UTF_8);
        ByteBuffer tags=ByteBuffer.allocate(16+vendor.length).order(ByteOrder.LITTLE_ENDIAN);
        tags.put("OpusTags".getBytes(StandardCharsets.US_ASCII)).putInt(vendor.length).put(vendor).putInt(0);
        page(tags.array(),0,0);
    }
    static int packetSamples(byte[] packet) throws IOException {
        if(packet.length<1)throw new IOException("Empty Opus packet");
        int toc=packet[0]&255,config=toc>>3,frame;
        if(config>=16)frame=120<<(config&3);
        else if(config>=12)frame=480<<(config&1);
        else frame=(config&3)==3?2880:480<<(config&3);
        int code=toc&3,count=code==0?1:code==3?(packet.length>1?packet[1]&63:0):2;
        if(count==0 || frame*count>5760)throw new IOException("Invalid Opus packet duration");
        return frame*count;
    }
    void packet(byte[] packet, boolean last, long endGranule) throws IOException {
        int segments=packet.length/255+1;
        if(segments>255)throw new IOException("Opus packet too large");
        if(lacing.size()+segments>255)flush(false,samples);
        int duration=packetSamples(packet);samples+=duration;pageSamples+=duration;
        packets.write(packet);
        for(int i=0;i<segments;i++)lacing.write(i==segments-1?packet.length%255:255);
        if(last)flush(true,endGranule>=0?Math.min(samples,endGranule):samples);
        else if(pageSamples>=48000)flush(false,samples);
    }
    private void flush(boolean last,long granule)throws IOException {
        if(lacing.size()==0)return;
        writePage(packets.toByteArray(),lacing.toByteArray(),last?4:0,granule);
        packets.reset();lacing.reset();pageSamples=0;
    }
    private void page(byte[] packet,int flags,long granule)throws IOException {
        int segments=packet.length/255+1;
        if(segments>255)throw new IOException("Opus packet too large");
        byte[] sizes=new byte[segments];
        for(int i=0;i<segments;i++)sizes[i]=(byte)(i==segments-1?packet.length%255:255);
        writePage(packet,sizes,flags,granule);
    }
    private void writePage(byte[] packet,byte[] sizes,int flags,long granule)throws IOException {
        ByteBuffer page=ByteBuffer.allocate(27+sizes.length+packet.length).order(ByteOrder.LITTLE_ENDIAN);
        page.put("OggS".getBytes(StandardCharsets.US_ASCII)).put((byte)0).put((byte)flags)
            .putLong(granule).putInt(serial).putInt(sequence++).putInt(0).put((byte)sizes.length);
        page.put(sizes);
        page.put(packet);byte[] bytes=page.array();int crc=0;
        for(byte b:bytes) {
            crc^=(b&255)<<24;
            for(int i=0;i<8;i++)crc=(crc<<1)^((crc&0x80000000)!=0?0x04c11db7:0);
        }
        page.putInt(22,crc);output.write(bytes);
    }
}
