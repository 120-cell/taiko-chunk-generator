# put in a directory with the audio file and background for the mapset
# time the song using the editor and enter the values below
# sort by BPM in osu to see the diffs in the intended order

# config

fingers_per_hand = 4
hands_per_chunk = 2
chunks_per_group = 8
chunks_introduced_per_diff = 4 # minimum 2
diffs_combined_at_a_time = 2 # minimum 2
tapping_order_starts_with_k = True

firs_note_ms = 11_280
last_note_ms = 203_280
bpm = 170
notes_per_beat = 2
minimum_notes_per_pause = 2

audio_filename = 'Bon Appetit S.mp3'
background_filename = 'Bon Appetit S.png'
title = 'Taiko Chunking Practice'
artist = 'unknown'
creator = '120\'s Chunk Generator'

overall_difficulty = 5
scroll_velocity = 0.7

# end of config


from distutils.dir_util import remove_tree
from math import sqrt, floor, ceil, log
from shutil import copy
import random
import os
import zipfile
import itertools


chunks_introduced_per_diff = max(2, chunks_introduced_per_diff)
diffs_combined_at_a_time = max(2, diffs_combined_at_a_time)
layout_length = fingers_per_hand * hands_per_chunk
if layout_length % 2 == 1:
    raise ValueError("fingers_per_hand * hands_per_chunk needs to be even")

ms_per_note = 60_000 / (notes_per_beat * bpm)
number_of_note_slots = round(notes_per_beat * bpm * (last_note_ms - firs_note_ms) / 60000) + 1

golden_ratio = (1+sqrt(5))/2


def push_chunks_to_list(layout_keys_left, next_color_in_layout, sequence, chunks):
    if layout_keys_left < 0:
        return False
    skip_is_valid = push_chunks_to_list(layout_keys_left - 2, next_color_in_layout, 
                                        sequence + [not next_color_in_layout], chunks)
    no_skip_is_valid = push_chunks_to_list(layout_keys_left - 1, not next_color_in_layout, 
                                           sequence + [next_color_in_layout], chunks)
    if not (skip_is_valid and no_skip_is_valid):
        chunks.append(sequence)
    return True


def generate_chunks(layout_length, starting_color):
    chunks = []
    push_chunks_to_list(layout_length, bool(starting_color), [], chunks)
    return chunks


def string_from_chunk(chunk):
    result = ''.join(['k' if bit else 'd' for bit in chunk])
    if chunk[-1] == (layout_length + tapping_order_starts_with_k) % 2:
        result += result[-1]
    return result



def make_chunk_list(chunks):
    with open('List of chunks.txt', 'w') as list_file:
        list_file.write('\n'.join([string_from_chunk(chunk) for chunk in chunks]))


def fibonacci(n):
    if n < 1 or not isinstance(n, int):
        raise ValueError("n must be a positive integer")
    f1 = 1
    f2 = 1
    for i in range(n-2):
        f3 = f1 + f2
        f1 = f2
        f2 = f3
    return f2


def number_to_base(n, base):
    if n == 0:
        return [0]
    digits = []
    while n:
        digits.append(int(n % base))
        n //= base
    return digits[::-1]


def describe_range(start, stop):
    if start == stop:
        return str(start)
    else:
        return f'{start}-{stop}'


def describe_integer_list(integers): # needs to be sorted
    if not integers:
        return 'empty list'
    
    description = ''
    start = integers[0]
    for i, integer in enumerate(integers):
        if integer > integers[i - 1] + 1:
            description += f'{describe_range(start, integers[i - 1])}, '
            start = integer
    description += describe_range(start, integers[-1])
    return description


def p_first_skip_to_equalize_frequencies(chunks_first_skip, chunks_no_first_skip, last_layout_note):
    p_no_last_skip_given_first_skip = sum([1 for chunk in chunks_first_skip if chunk[-1] == last_layout_note])
    if p_no_last_skip_given_first_skip:
        p_no_last_skip_given_first_skip /= len(chunks_first_skip)
    p_no_last_skip_given_no_first_skip = sum([1 for chunk in chunks_no_first_skip if chunk[-1] == last_layout_note])
    if p_no_last_skip_given_no_first_skip:
        p_no_last_skip_given_no_first_skip /= len(chunks_no_first_skip)

    possibility_1 = p_no_last_skip_given_no_first_skip
    possibility_2 = chunks_first_skip and (not chunks_no_first_skip) and (p_no_last_skip_given_first_skip == 1)
    possibility_3 = chunks_no_first_skip and (not chunks_first_skip) and (p_no_last_skip_given_no_first_skip == 0)
    if not (possibility_1 or possibility_2 or possibility_3):
        raise ValueError(f"""chunk set must fulfill one of the following:
                         contain at least one chunk that skips neither the first nor the last note,
                         only contain chunks that skip the first note, but not the last,
                         or only contain chunks that skip the last note, but not the first.
                         Faulty chunks:
                         first skip: {chunks_first_skip}
                         no first skip: {chunks_no_first_skip}""")
    
    natural_p_first_skip = len(chunks_first_skip) / (len(chunks_first_skip) + len(chunks_no_first_skip))
    if possibility_3:
        p_first_skip = 0
    else:
        p_first_skip  = natural_p_first_skip / (p_no_last_skip_given_no_first_skip
            + natural_p_first_skip * (p_no_last_skip_given_first_skip - p_no_last_skip_given_no_first_skip))
    if p_first_skip > 1:
        print(f"""Warning. Not all chunks will appear with equal frequency in the following diff:
              first skip {chunks_first_skip}
              no first skip {chunks_no_first_skip}""")
    return p_first_skip


def generate_hitobjects(chunks, selected_chunk_indices):
    current_note_slot = 0
    hitobjects = []
    
    selected_chunks = [chunks[chunk_index] for chunk_index in selected_chunk_indices]
    chunks_first_skip = [chunk for chunk in selected_chunks if chunk[0] != tapping_order_starts_with_k]
    chunks_no_first_skip = [chunk for chunk in selected_chunks if chunk[0] == tapping_order_starts_with_k]
    last_layout_note = (layout_length - 1 + tapping_order_starts_with_k) % 2
    p_first_skip = p_first_skip_to_equalize_frequencies(chunks_first_skip,
                                                        chunks_no_first_skip,
                                                        last_layout_note)
    
    previous_chunk_end = last_layout_note
    while current_note_slot < number_of_note_slots - 1:
        for chunk_counter in range(chunks_per_group):
            if (previous_chunk_end == last_layout_note) and (random.random() < p_first_skip):
                new_chunk = random.choice(chunks_first_skip)
            else:
                new_chunk = random.choice(chunks_no_first_skip)
            previous_chunk_end = new_chunk[-1]
            
            for note in new_chunk:
                if current_note_slot < number_of_note_slots - 1:
                    time = firs_note_ms + ms_per_note * current_note_slot
                    hitsound = 8 if note else 1
                    hitobjects.append(f'256,192,{time},1,{hitsound},0:0:0:0:')
                    current_note_slot += 1
            
        current_note_slot += 2
        current_note_slot += (-current_note_slot) % notes_per_beat
        
    return hitobjects
    
    
def make_diff(chunks, selected_chunk_indices, diff_counter):
    diff_name = f'Chunk {describe_integer_list([i + 1 for i in selected_chunk_indices])}'
    hitobject_list = generate_hitobjects(chunks, selected_chunk_indices)
    hitobject_string = '\n'.join(hitobject_list)
    osu_file_text = f"""osu file format v14

[General]
AudioFilename: {audio_filename}
AudioLeadIn: 0
PreviewTime: -1
Countdown: 0
SampleSet: Normal
StackLeniency: 0.7
Mode: 1
LetterboxInBreaks: 0
WidescreenStoryboard: 0

[Editor]
DistanceSpacing: 1
BeatDivisor: 4
GridSize: 32
TimelineZoom: 1

[Metadata]
Title:{title}
TitleUnicode:{title}
Artist:{artist}
ArtistUnicode:{artist}
Creator:{creator}
Version:{diff_name}
Source:
Tags:
BeatmapID:0
BeatmapSetID:-1

[Difficulty]
HPDrainRate:5
CircleSize:5
OverallDifficulty:{overall_difficulty}
ApproachRate:5
SliderMultiplier:{scroll_velocity}
SliderTickRate:1

[Events]
//Background and Video events
0,0,"{background_filename}",0,0
//Break Periods
//Storyboard Layer 0 (Background)
//Storyboard Layer 1 (Fail)
//Storyboard Layer 2 (Pass)
//Storyboard Layer 3 (Foreground)
//Storyboard Layer 4 (Overlay)
//Storyboard Sound Samples

[TimingPoints]
{firs_note_ms},{60_000/bpm},4,0,0,100,1,0
{last_note_ms},{60_000/(bpm + diff_counter)},4,0,0,100,1,0

[HitObjects]
{hitobject_string}
"""
    with open(f'temp/{artist} - {title} ({creator}) [{diff_name}].osu', 'w') as osu_file:
        osu_file.write(osu_file_text)


def reorder_chunks(chunks):
    number_of_introductions = ceil(len(chunks) / chunks_introduced_per_diff)
    
    first_key = tapping_order_starts_with_k
    last_key = (first_key + layout_length - 1) % 2
    
    chunks_first_skip = [chunk for chunk in chunks if chunk[0] != first_key and chunk[-1] == last_key]
    chunks_both_skip = [chunk for chunk in chunks if chunk[0] != first_key and chunk[-1] != last_key]
    chunks_neither_skip = [chunk for chunk in chunks if chunk[0] == first_key and chunk[-1] == last_key]
    chunks_last_skip = [chunk for chunk in chunks if chunk[0] == first_key and chunk[-1] != last_key]
    
    reserved_neither_skip = chunks_neither_skip[:min(number_of_introductions, len(chunks_neither_skip))]
    still_to_fill = number_of_introductions - len(reserved_neither_skip)
    fillable_from_first_skip = min(still_to_fill, len(chunks_first_skip) // chunks_introduced_per_diff)
    reserved_first_skip = chunks_first_skip[:fillable_from_first_skip * chunks_introduced_per_diff]
    still_to_fill -= fillable_from_first_skip
    reserved_last_skip = chunks_last_skip[:still_to_fill * chunks_introduced_per_diff]
    
    zipped_rest_chunks = itertools.zip_longest(chunks_first_skip[len(reserved_first_skip):],
                                               chunks_both_skip,
                                               chunks_neither_skip[len(reserved_neither_skip):],
                                               chunks_last_skip[len(reserved_last_skip):])
    rest_chunks = [x for x in itertools.chain(*zipped_rest_chunks) if x is not None]
    
    reordered_chunks = reserved_first_skip
    for neither_skip in reserved_neither_skip[:-1]:
        reordered_chunks.append(neither_skip)
        for i in range(chunks_introduced_per_diff - 1):
            if rest_chunks:
                reordered_chunks.append(rest_chunks.pop(0))
    reordered_chunks += reserved_last_skip
    reordered_chunks.append(reserved_neither_skip[-1])
    for i in range(chunks_introduced_per_diff - 1):
        if rest_chunks:
            reordered_chunks.append(rest_chunks.pop(0))
    return reordered_chunks


def make_diffs(chunks):
    introduction_ranges = []
    for introduction_counter in range(len(chunks) // chunks_introduced_per_diff):
        introduction_ranges.append(range(introduction_counter * chunks_introduced_per_diff,
                                         (introduction_counter + 1) * chunks_introduced_per_diff))
    if len(chunks) % chunks_introduced_per_diff:
        introduction_ranges.append(range((introduction_counter + 1) * chunks_introduced_per_diff,
                                         len(chunks)))
    
    diff_counter = 0 
    for introduction_counter, introduction_range in enumerate(introduction_ranges):
        print(f'making introduction diff nr. {introduction_counter}')
        make_diff(chunks, introduction_range, diff_counter)
        diff_counter += 1
        
        hierarchy = number_to_base(introduction_counter,  diffs_combined_at_a_time)[::-1]
        next_hierarchy = number_to_base(introduction_counter + 1, diffs_combined_at_a_time)[::-1]
        for hierarchy_level, (digit, next_digit) in enumerate(itertools.zip_longest(hierarchy, next_hierarchy, fillvalue=0)):
            difference = next_digit - digit
            if digit and difference:
                diff_range_start = introduction_counter + 1 - (digit + 1) * (diffs_combined_at_a_time ** hierarchy_level)
                diff_range_end = introduction_counter + 1
                combined_chunk_range = list(itertools.chain(*introduction_ranges[diff_range_start:diff_range_end]))
                print(f'making level {hierarchy_level} diff using intro diff {describe_range(diff_range_start, diff_range_end - 1)}')
                make_diff(chunks, combined_chunk_range, diff_counter)
                diff_counter += 1
    
    first_non_zero_level = next(level for level, digit in enumerate(hierarchy))
    for hierarchy_level in range(first_non_zero_level + 1, len(hierarchy)):
        digit = hierarchy[hierarchy_level]
        if digit:
            diff_range_start = sum([hierarchy[i] * diffs_combined_at_a_time**i
                                    for i in range(hierarchy_level + 1, len(hierarchy))])
            diff_range_end = len(introduction_ranges)
            combined_chunk_range = list(itertools.chain(*introduction_ranges[diff_range_start:diff_range_end]))
            print(f'making level {hierarchy_level} diff using intro diff {describe_range(diff_range_start, diff_range_end - 1)}')
            make_diff(chunks, combined_chunk_range, diff_counter)
            diff_counter += 1
    
        
def zipdir(source_path, destination_path):
    with zipfile.ZipFile(destination_path, 'w', zipfile.ZIP_DEFLATED) as destination_file:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                destination_file.write(os.path.join(root, file),
                                       os.path.relpath(os.path.join(root, file), 
                                                       source_path))


def main():
    chunks = generate_chunks(layout_length, tapping_order_starts_with_k)
    reordered_chunks = reorder_chunks(chunks)
    make_chunk_list(reordered_chunks)

    if os.path.isdir('temp'):
        remove_tree('temp')
    os.mkdir('temp')
    copy(audio_filename, 'temp')
    copy(background_filename, 'temp')
    make_diffs(reordered_chunks)
    zipdir('temp', f'{title}.osz')
    remove_tree('temp')

if __name__ == 'main':
    main()
