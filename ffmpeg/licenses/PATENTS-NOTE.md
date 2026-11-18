# Patents

The copyright licences of `licenses/` grant no patent licence, and neither does this archive.

* FFmpeg's own software decoders for H.264, HEVC, MPEG-2, MPEG-4 Part 2, VC-1, AAC, AC-3, E-AC-3, DTS and the other
  formats of `BUILD-INFO.txt`, and its AAC encoder, are in the archive. Some of these formats are covered by patents in
  some countries; whether a licence is needed where you use them is for you to check.
* H.264 and HEVC encoding goes through the encoders of the system: Media Foundation on Windows (`h264_mf`, `hevc_mf`),
  VideoToolbox on macOS (`h264_videotoolbox`, `hevc_videotoolbox`) and the VA-API drivers installed on Linux
  (`h264_vaapi`, `hevc_vaapi`). No H.264 or HEVC encoder of its own is in the archive (no libx264, libx265 or
  OpenH264).
* AV1 comes with the royalty free Alliance for Open Media Patent License 1.0, whose text SVT-AV1 ships
  (`SVT-AV1-PATENTS.md`): the AV1 encoder (SVT-AV1) and decoder (dav1d) of the archive implement that format.
