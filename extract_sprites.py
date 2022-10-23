#!/usr/bin/env python

# -*- coding: utf-8 -*-

import os
from PIL import Image

GRANDPRIX_SOURCE_DIR = 'grandprix'
SPRITE_DEST_DIR = 'sprites'

COLORSPACE_CGA = \
    [ (  0,  0,  0, 255), (  0, 255, 255, 255), (255,   0, 255, 255), (255, 255, 255, 255) ]

COLORSPACE_EGA = \
    [ (  0,  0,  0, 255), (  0,   0, 170, 255), (  0, 170,   0, 255), (  0, 170, 170, 255),
      (170,  0,  0, 255), (170,   0, 170, 255), (170,  85,   0, 255), (170, 170, 170, 255),
      ( 85, 85, 85, 255), ( 85,  85, 255, 255), ( 85, 255,  85, 255), ( 85, 255, 255, 255),
      (255, 85, 85, 255), (255,  85, 255, 255), (255, 255,  85, 255), (255, 255, 255, 255) ]

class PackedSpriteFile:
    def __init__(self, filename):
        self.__color_space = None
        self.__detect_color_space(filename)

        # file header
        self.__unpacked_content_length = 0
        self.__packed_content_length = 0
        self.__run_length_markers = { }
        self.__skip_unpack_phase1 = False
        # unpacked contents
        self.__contents = [ ]
        self.__content_bytes_read = 0
        self.__load_contents(filename)

        # table of contents
        self.__sprites = { }
        self.__parse_sprite_list()


    def __detect_color_space(self, filename):
        (base, ext) = os.path.splitext(filename)
        if ext.upper() == '.PCS':
            self.__color_space = COLORSPACE_CGA
        elif ext.upper() == '.PES':
            self.__color_space = COLORSPACE_EGA
        else:
            raise Exception('Unsupported file type')


    def __read_bytes_header(self, f, length):
        return int.from_bytes(f.read(length), byteorder='little')


    def __read_header(self, f):
        self.__unpacked_content_length = self.__read_bytes_header(f, 4)
        self.__packed_content_length = self.__read_bytes_header(f, 4)

        amount_run_length_markers = self.__read_bytes_header(f, 1)

        for i in range(amount_run_length_markers & 0x0F):
            rep_marker = self.__read_bytes_header(f, 1)
            if rep_marker not in self.__run_length_markers:
                self.__run_length_markers[rep_marker] = i

        if amount_run_length_markers & 0xF0 == 0x80:
            self.__skip_unpack_phase1 = True


    def __read_bytes(self, f, length):
        self.__content_bytes_read += length
        if self.__content_bytes_read > self.__packed_content_length:
            raise Exception('Read beyond end of file (%d > %d)' \
                                    % (self.__content_bytes_read, self.__packed_content_length))
        return self.__read_bytes_header(f, length)


    def __find_sequence(self, f):
        rep_markers_keys = list(self.__run_length_markers.keys())
        rep_markers_values = list(self.__run_length_markers.values())
        rep1_marker = rep_markers_keys[rep_markers_values.index(1)]

        sequence_buffer = [ ]
        seq_b = self.__read_bytes(f, 1)
        while seq_b != rep1_marker:
            sequence_buffer.append(seq_b)
            seq_b = self.__read_bytes(f, 1)

        return sequence_buffer


    def __unpack_content_phase1(self, f):
        self.__content_bytes_read = 0
        while self.__content_bytes_read < self.__packed_content_length:
            b = self.__read_bytes(f, 1)
            if not self.__skip_unpack_phase1 \
               and b in self.__run_length_markers \
               and self.__run_length_markers[b] == 1:
                # this indicates the start of a sequence to be repeated
                # the sequence ends at the same byte
                sequence_buffer = self.__find_sequence(f)
                # followed by the run length
                seq_run_length = self.__read_bytes(f, 1)
                for i in range(seq_run_length):
                    for j in sequence_buffer:
                        yield j
            else:
                yield b


    def __unpack_content(self, f):
        phase1_contents = self.__unpack_content_phase1(f)
        while self.__content_bytes_read < self.__packed_content_length:
            b = phase1_contents.__next__()
            if b in self.__run_length_markers:
                run_length = self.__run_length_markers[b]
                if run_length == 0:
                    # next byte is real amount
                    run_length = phase1_contents.__next__()
                elif run_length == 2:
                    # next 2 bytes is real amount
                    run_length = phase1_contents.__next__() + (phase1_contents.__next__() << 8)
                # add next byte amount times
                next_b = phase1_contents.__next__()
                self.__contents += [ next_b ] * run_length
            else:
                self.__contents.append(b)

        if len(self.__contents) != self.__unpacked_content_length:
            # warning only, there are official files with this problem
            print('Unpacked content size mismatch: expected %d but is %d' \
                                    % (self.__unpacked_content_length, len(self.__contents)))


    def __load_contents(self, filename):
        with open(filename, 'rb') as f:
            self.__read_header(f)
            self.__unpack_content(f)


    def __get_string(self, offset, length):
        return ''.join([ chr(c) for c in self.__contents[offset : offset + length] if c != 0 ])


    def __get_int(self, offset, length):
        return int.from_bytes(self.__contents[offset : offset + length], byteorder='little')


    def __parse_sprite_list(self):
        # self.unpacked_content_length is again at the first 4 bytes
        amount_sprites = int.from_bytes(self.__contents[4:6], byteorder='little')
        for i in range(amount_sprites):
            sprite_name = self.__get_string(6+i*4, 4)
            sprite_offset = self.__get_int(6+amount_sprites*4+i*4, 4)
            if sprite_offset > self.__unpacked_content_length:
                raise Exception('Sprite offset beyond end of unpacked contents (%d > %d)' \
                                    % (sprite_offset, self.__unpacked_content_length))
            self.__sprites[sprite_name] = sprite_offset


    def get_sprite_list(self):
        return list(self.__sprites.keys())


    def __get_pixel_color_cga(self, offset, layer_info, width, height, x, y):
        # Note: it is less CPU intensive to write separate functions for the existing 4 types than
        #       to evaluate layer_info for every pixel
        if layer_info & 0xffff0000 == 0x00000000:
            # CGA non-interlaced horiz-first
            pixel_byte = self.__contents[offset + (x // 4) + y * (width // 4)]
            return self.__color_space[(pixel_byte >> (2 * (3 - x%4))) % 4]
        elif layer_info & 0xffff0000 == 0x00100000:
            # CGA non-interlaced vert-first
            pixel_byte = self.__contents[offset + (x // 4) * height + y]
            return self.__color_space[(pixel_byte >> (2 * (3 - x%4))) % 4]
        elif layer_info & 0xffff0000 == 0x00200000:
            # CGA interlaced vert-first
            new_offset = offset + abs(height % 2 - y % 2) * (height // 2)
            pixel_byte = self.__contents[new_offset + (x // 4) * height + (y // 2)]
            return self.__color_space[(pixel_byte >> (2 * (3 - x%4))) % 4]
        elif layer_info & 0xffff0000 == 0x00300000:
            # CGA interlaced vert-first, alternate bytes between first and second half
            new_offset = offset + (y % 2) * width * (height + (height % 2)) // 8
            corrected_height = height + (1 - (y % 2) * 2) * (height % 2)
            pixel_byte = self.__contents[new_offset + ((x // 4) * corrected_height + y) // 2]
            return self.__color_space[(pixel_byte >> (2 * (3 - x%4))) % 4]
        else:
            # fallback for unknown types - transparent
            return 0


    def __get_pixel_color_ega(self, offset, layer_info, width, height, x, y):
        # EGA layered BGRI
        # layer mapping:
        # layer_info & 0xf0000000: not used
        # layer_info & 0x0f000000: color(s) on layer 3
        # layer_info & 0x00f00000: color(s) to suppress
        # layer_info & 0x000f0000: color(s) on layer 2
        # layer_info & 0x0000f000: background color
        # layer_info & 0x00000f00: color(s) on layer 1
        # layer_info & 0x000000f0: layer(s) stored vertically
        # layer_info & 0x0000000f: color(s) on layer 0
        vert_offset = (x // 8) * height + y
        horiz_offset = (x // 8) + y * (width // 8)
        plane_size = width * height // 8

        rgb_plane = 4
        pixel_color = 0
        while rgb_plane > 0:
            rgb_plane -= 1

            layer_info_mask = 1 << rgb_plane
            mapped_plane = -1
            for i in range(4):
                if (layer_info >> (i*8)) & layer_info_mask == layer_info_mask:
                    mapped_plane = i

            if mapped_plane != -1:
                plane_direction_mask = pow(2, mapped_plane) << 20
                if layer_info & plane_direction_mask == plane_direction_mask:
                    pixel_byte = self.__contents[offset + mapped_plane * plane_size + vert_offset]
                else:
                    pixel_byte = self.__contents[offset + mapped_plane * plane_size + horiz_offset]
                pixel_color = (pixel_color << 1) + ((pixel_byte >> (7 - x % 8)) % 2)
            else:
                pixel_color = (pixel_color << 1)

        background_color = (layer_info >> 12) & 0xf

        return self.__color_space[background_color ^ pixel_color]


    def __get_bitmap(self, spritename):
        base_offset = 6 + 8 * len(self.__sprites)
        offset = base_offset + self.__sprites[spritename]
        width = self.__get_int(offset, 2)
        height = self.__get_int(offset + 2, 2)
        print('%s: ' % spritename, end='')
        for i in range(12):
            print('%02x ' % self.__get_int(offset + 4 + i, 1), end='')
        print()
        # TODO offset 4-7 ???
        pos_x = self.__get_int(offset + 8, 2)
        pos_y = self.__get_int(offset + 10, 2)
        layer_info = self.__get_int(offset + 12, 4)

        get_pixel_color = lambda offset, layer_info, width, height, x, y: 0
        if self.__color_space == COLORSPACE_CGA:
            width *= 4 # CGA 4 pixels per byte
            get_pixel_color = self.__get_pixel_color_cga
        elif self.__color_space == COLORSPACE_EGA:
            width *= 8 # EGA 2 pixels per byte * 4 color planes
            get_pixel_color = self.__get_pixel_color_ega

        bitmap = [ ]
        for x in range(width):
            bitmap_column = [ ]
            for y in range(height):
                pixel_color = get_pixel_color(offset + 16, layer_info, width, height, x, y)
                bitmap_column.append(pixel_color)
            bitmap.append(bitmap_column)

        return (width, height, pos_x, pos_y, bitmap)


    def save_image(self, spritename, filename):
        (width, height, pos_x, pos_y, bitmap) = self.__get_bitmap(spritename)

        image = Image.new('RGBA', (width, height))
        for x in range(width):
            for y in range(height):
                image.putpixel((x, y), bitmap[x][y])
        image.save(filename)


    def build_screen(self, spritenames, filename):
        image = Image.new('RGBA', (320, 200))
        for spritename in spritenames:
            (width, height, pos_x, pos_y, bitmap) = self.__get_bitmap(spritename)

            for x in range(width):
                for y in range(height):
                    image.putpixel((pos_x + x, pos_y + y), bitmap[x][y])

        image.save(filename)


    def dump_unpacked_contents(self, filename):
        print('Dumping %d bytes to %s' % (len(self.__contents), filename))
        with open(filename, 'wb') as f:
            f.write(bytearray(self.__contents))



def main():
    # create directory for the extracted sprites
    try:
        os.mkdir(SPRITE_DEST_DIR)
    except FileExistsError:
        pass

    for filename in os.listdir(GRANDPRIX_SOURCE_DIR):
        (basename, ext) = os.path.splitext(filename)
        if ext in [ '.PCS', '.PES' ]:
            full_path_name = os.path.join(GRANDPRIX_SOURCE_DIR, filename)
            print('Processing %s' % full_path_name)
            try:
                sprite_file = PackedSpriteFile(full_path_name)
                for sprite in sprite_file.get_sprite_list():
                    output_filename = os.path.join(SPRITE_DEST_DIR, filename) + '.' + sprite + '.png'
                    sprite_file.save_image(sprite, output_filename)
            except Exception as e:
                # continue to the next file
                print(e)
                pass


main()
