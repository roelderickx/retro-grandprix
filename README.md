# Grand Prix Circuit

This repository contains documentation on the file format of the Grand Prix game by Distinctive Software, released by Accolade in 1988. Information on the original game can be found on [wikipedia](https://en.wikipedia.org/wiki/Grand_Prix_Circuit_(video_game)).

It turns out to work more or less for [The Cycles](https://en.wikipedia.org/wiki/The_Cycles:_International_Grand_Prix_Racing) as well, released a year later from the same publisher.

# Proof of concept

An installation of python 3 is required to run the proof of concept. Create a subdirectory called `grandprix` and put the original game in this directory before running `extract-sprites.py`. All sprites from all PCS (4 colors CGA) and PES (16 colors EGA) files in the grandprix directory will be unpacked to a new directory called `sprites`.

## The Cycles

A quick test reveals the proof of concept works for The Cycles as well, but there are some caveats:

- Each file contains a sprite called PAT!, which does not actually contain sprite data. To be investigated.
- The PAT! sprite may not extract properly on Windows since ! is not an allowed character for filenames
- The uncompressed content size reported in the header does not match the actual size obtained after decompression. The proof of concept issues a warning but will continue unpacking. Converting the advertised value and the real value to hexadecimal sheds some light on this issue. For example both values in _Unpacked content size mismatch: expected 8584449 but is 33533_ convert to 82FD01 and 82FD respectively.

# Compression

The compression is basically a run length encoding.

Every file starts with a header:
| offset | length | description
| ------ | ------ | -----------
| 0x00 | 4 | unpacked content length
| 0x04 | 4 | packed content length (should be filesize - header size)
| 0x08 | 1 | high nibble: 8 means the first step of the decompression must be skipped, low nibble: amnt = amount of run length markers, usually 10
| 0x09 | amnt | run length markers, defining an array RLM[0..amnt-1]

This information allows for the decompression of the contents, which follows immediately after the header. The decompression has to be done in two steps:

1. The series of bytes between two RLM[1] bytes has to be repeated n times, where n is the byte to be found after the second RLM[1] byte
2. RLM[n] is replaced by n times the byte following RLM[n]. There are exceptions for RLM[0] and RLM[2], as it does not make sense to repeat a given byte 0 or 2 times.
    - For RLM[0] the next byte indicates the amount to be repeated
    - For RLM[2] the next two bytes indicate the amount to be repeated

# Sprites

The content starts with an index of the sprites, each identified by a string of max 4 characters.

## Sprite index

| offset | length | description
| ------ | ------ | -----------
| 0x00 | 4 | unpacked content length (same as in header)
| 0x04 | 2 | amnt = amount of sprites
| 0x06 | 4 x amnt | sprite names
| 0x06 + 4 x amnt | 4 x amnt | sprite offsets (0x00 is the first byte after the sprite index)

## Sprite data

After the sprite index follows the sprite data. Individual sprites can be found by their offset, the length of the data is not specified but can be calculated from the width, height and amount of colors.
Sprites are defined by a sprite header followed by the actual sprite data.

### Sprite header

| offset | length | description
| ------ | ------ | -----------
| 0x00 | 2 | width in bytes. Multiply by 4 for CGA or 8 for EGA (4 monochrome layers for RGB and intensity) to get the width in pixels
| 0x02 | 2 | height
| 0x04 | 4 | these 4 bytes have an unclear function, to be investigated
| 0x08 | 2 | position on screen x-coordinate
| 0x0A | 2 | position on screen y-coordinate
| 0x0C | 4 | layer info, see below

#### Sprite layer info

Pixels are not always added from left to right and from top to bottom, in stead the order is presumably chosen to achieve the highest compression rate.

##### CGA 4 colours

- 0x00000000: pixels are stored horizontally
- 0x00100000: pixels are stored vertically, in columns of 4 pixels (1 byte contains 4 pixels)
- 0x00200000: pixels are stored vertically, in columns of 4 pixels, but interlaced (this is how CGA graphic cards work, it may be chosen to achieve performance in stead of a high compression rate)
- 0x00300000: difficult to explain, combination of two half-images which are also interlaced. see the proof of concept implementation.

##### EGA 16 colours

EGA graphic adapters store the image on screen as 4 monochrome color planes: red, green, blue and intensity. This is reflected in the sprite data, but to minimize the file size there are three optimisations implemented:

- Color planes containing all zeroes are omitted
- Color planes containing all ones are omitted as well but defined as background color
- If two or more colors share the same color plane information it is stored only once

Each of the 8 nibbles in the 32-bit layer_info value contains information on how to reconstruct each color plane.

- layer_info & 0xf0000000: not used
- layer_info & 0x0f000000: color(s) on layer 3
- layer_info & 0x00f00000: color(s) to suppress (color planes containing all zeroes)
- layer_info & 0x000f0000: color(s) on layer 2
- layer_info & 0x0000f000: background color (color planes containing all ones)
- layer_info & 0x00000f00: color(s) on layer 1
- layer_info & 0x000000f0: layer(s) stored vertically, in columns of 8 pixels
- layer_info & 0x0000000f: color(s) on layer 0

### Layer data

The sprite layer(s) are following the sprite header. In case of CGA there will be exactly 1 layer, in case of EGA there can be up to 4 layers (there is usually at least 1 layer, but theoretically it is possible to have no layers at all when there is only 1 background color).
The size in bytes of a layer can be calculated as `width x height / pixels_per_byte`. In CGA mode there are 4 pixels per byte, in EGA there are 8 since each layer is monochrome.

# Music

There are two files with a .BIN extension which contain the music, one tune per file. There is also one file with a .SND extension which contains two sounds. All music and sound files are uncompressed, the header of the .SND file is the same as for the sprites:

| offset | length | description
| ------ | ------ | -----------
| 0x00 | 4 | content length
| 0x04 | 2 | amount of sounds
| 0x06 | 4 x amnt | sound names
| 0x06 + 4 x amnt | 4 x amnt | sound offsets (0x00 is the first byte after the data header)

## Music data

This is work in progress. Generally speaking:

- Each note is represented as three bytes
- A series of notes can be repeated several times, each time in a different octave
- The sound generated by the game is a block wave in stead of a sine wave

