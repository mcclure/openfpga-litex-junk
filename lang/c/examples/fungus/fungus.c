// Fluidly expanding colors
// Sample contributed by Andi McClure, available under Creative Commons Zero (public domain)
// If you substantially reuse this code a credit would be appreciated but is not required

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>

// #include <irq.h>
// #include <libbase/uart.h>
// #include <libbase/console.h>
#include <generated/csr.h>

// Turn on to print warnings when frame fails to draw within vblank
#define SPEED_DEBUG 0

#define DISPLAY_WIDTH 266
#define DISPLAY_HEIGHT 240

#define BITS5 ((1<<5)-1)
#define BITS6 ((1<<6)-1)
// Takes 3 numbers in range 0..64. Lowest bit on R and B will be discarded.
#define COLOR(r,g,b) ( ( (((r)>>1)&BITS5)<<11 ) | ( ((g)&BITS6)<<5 ) | ( (((b)>>1)&BITS5) ))

typedef enum {
    dpad_up     = 1<<0,
    dpad_down   = 1<<1,
    dpad_left   = 1<<2,
    dpad_right  = 1<<3,
    face_a      = 1<<4,
    face_b      = 1<<5,
    face_x      = 1<<6,
    face_y      = 1<<7,
    trig_l1     = 1<<8,
    trig_r1     = 1<<9,
    trig_l2     = 1<<10,
    trig_r2     = 1<<11,
    trig_l3     = 1<<12,
    trig_r3     = 1<<13,
    face_select = 1<<14,
    face_start  = 1<<15,
} PocketControls;

// Sizes and spacing of "pillar" squares
#define PILLAR_COUNT 3
#define PILLAR_SIZE 40
#define PILLAR_GAP 30
#define PILLAR_COLOR (COLOR(20, 0, 0))
#define PILLARS_SIZE (PILLAR_GAP*(PILLAR_COUNT-1)+PILLAR_SIZE*PILLAR_COUNT)
// Given an axis of size n, what offset is needed to center the group of pillars?
#define PILLARS_BASE(n) (((n)-PILLARS_SIZE)/2)

// Candidate buffer size
#define CANDIDATE_TRUE_MAX 1600

// How full to keep audio buffer and how much to amplify
// AUDIO_GAP must be at least 2; if it's above 2, gaps will be put between wavebumps
// Setting AUDIO_SCALE to 256 and AUDIO_GAP to 4 is also pretty fun
#define AUDIO_TARGET (48000/60 + 200)
#define AUDIO_SCALE 128
#define AUDIO_CEILING (1<<15)
#define AUDIO_GAP 2
#define AUDIO_BEEP_BASE 5
#define AUDIO_BEEP_TIME (48000/AUDIO_BEEP_BASE/2)
#define AUDIO_BEEP_VOLUME ((1<<16)/32)

#define SPEED_COUNT 3

// What index within the framebuffer is this pixel at?
#define AT(x,y) (((y)*DISPLAY_WIDTH)+(x))

typedef struct {
    uint16_t x;
    uint16_t y;
} Candidate;

inline Candidate make_candidate(int x, int y) {
    Candidate candidate = {x,y};
    return candidate;
}

// Standalone random number generator
#include "xoshiro128starstar.h"

// Will use for colors
static inline uint32_t xo_rotr(const uint32_t x, int k) {
    return (x >> k) | (x << (32 - k));
}

// Fisher-Yates Shuffle, modeled on discussion at https://stackoverflow.com/a/42322025
// This will efficiently reorder an array randomly
static void fisher_yates(Candidate *array, int len) {
     Candidate temp;

     for (int idx_ceiling = len-1; idx_ceiling > 0; idx_ceiling--) { // Iterate array backward
         int idx_rand = xo_rand(idx_ceiling + 1); // Swap each member with a random member below it 
         if (idx_ceiling != idx_rand) {
             temp = array[idx_ceiling];
             array[idx_ceiling] = array[idx_rand];
             array[idx_rand] = temp;
         }
     }
}

static void beep(uint16_t set_beep_speed, uint16_t audio_wave, bool *audio_beeping, uint16_t *audio_beep_speed, uint16_t *audio_beep_time, int16_t *audio_beep_sign) {
    *audio_beeping = true;
    *audio_beep_speed = set_beep_speed;
    *audio_beep_time = 0;
    *audio_beep_sign = audio_wave > (1<<15) ? -1 : 1;
}

#define BEEP(set_beep_speed) beep((set_beep_speed), audio_wave, &audio_beeping, &audio_beep_speed, &audio_beep_time, &audio_beep_sign);


int main(void)
{
    printf("-- Fungus --\n");

    uint16_t *fb = (uint16_t *)(uintptr_t)video_framebuffer_dma_base_read();

    // Fill screen with black
    for(int c = 0; c < DISPLAY_WIDTH*DISPLAY_HEIGHT; c++)
        fb[c] = 0;

    { // Primitive randomness seed
        uint32_t time = apf_rtc_unix_seconds_read();
        xo_jump(time+5, time+3, time+2, time);
    }

    // Draw a 3x3 grid of rectangles with a hole in the middle, to break up the field
    int y_root = PILLARS_BASE(DISPLAY_HEIGHT), x_root = PILLARS_BASE(DISPLAY_WIDTH);
    {
        for(int by = 0; by < 3; by++) {
            for(int bx = 0; bx < 3; bx++) {
                if (bx == (PILLAR_COUNT/2) && by == (PILLAR_COUNT/2)) // Hole
                    continue;
                int y_block = y_root+by*(PILLAR_SIZE+PILLAR_GAP), x_block = x_root+bx*(PILLAR_SIZE+PILLAR_GAP);
                for(int y = 0; y < PILLAR_SIZE; y++) {
                    for(int x = 0; x < PILLAR_SIZE; x++) {
                        fb[AT(x_block+x, y_block+y)] = PILLAR_COLOR;
                    }
                }
            }
        }
    }

    // Who needs a heap anyway
    Candidate candidates[2][CANDIDATE_TRUE_MAX];
    int candidates_len[2] = {0,0};
    int current = 0;
    int color = COLOR(0,32,0);
    #define SHADOW_FRAMEBUFFER_SIZE ((DISPLAY_WIDTH*DISPLAY_HEIGHT)/8)
    static uint8_t shadow_framebuffer[SHADOW_FRAMEBUFFER_SIZE]; // Too big for stack

    // "Candidates" are points which are currently drawing,
    // "winners" are points that are currently being drawn
    // Col 1 is candidate count, col 2 is winner ratio (when winner_cut on), col 3 is beep speed
    const int speeds[SPEED_COUNT][3] = { {100, 10, 1}, {400, 4, 2}, {1600, 2, 4} };

    // Start descending from signed 0 to avoid a pop at the beginning
    uint16_t audio_cycle = 1;
    uint16_t audio_silence = 0;
    uint16_t audio_wave = 1<<15;
    uint16_t audio_wave_ceil = 0;
    bool audio_beeping = false;
    uint16_t audio_beep_speed = 1;
    uint16_t audio_beep_time = 0;
    uint16_t audio_beep_sign = 1;

    bool paused = false;
    uint16_t cont1_key_last = 0;

    bool super_grow = false;
    bool super_cycle = false;
    bool winner_cut = true;
    int speed = 1;

    while (1)
    {
        while (1) {
            uint32_t video = apf_video_video_read();
            if (apf_video_video_vblank_triggered_extract(video))
                break;
        }

        // At any one time we have two lists of points we can expand into;
        // one for the current frame, and one for the next frame.
        int next = (current+1)%2;
        Candidate *candidates_current = &candidates[current][0];
        Candidate *candidates_next = &candidates[next][0];

        #define CANDIDATE_PUSH(candidate) { candidates_next[candidates_len[next]] = candidate; candidates_len[next]++; }

        if (candidates_len[current] == 0) {
            candidates_current[0] = make_candidate(DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2);
            candidates_len[current] = 1;
        }

        // Draw the current list (but only the lucky first handful)
        int candidates_max = speeds[speed][0];
        int winner_count = candidates_max;
        if (winner_cut) winner_count /= speeds[speed][1];
        for(int idx = 0; idx < winner_count && idx < candidates_len[current]; idx++) {
            Candidate winner = candidates_current[idx];
            fb[AT(winner.x, winner.y)] = color;
        }

        // Do audio
        // We will generate a triangle wave which randomly changes its frequency each cycle.
        // Lower-pitched cycles are louder and higher-pitched cycles are quieter
        // I intended this to sound like fungus growing. And it doesn't,
        // but it did wind up sounding like a kind of bubbling cauldron, which I like.
        size_t audio_needed = AUDIO_TARGET - apf_audio_buffer_fill_read();
        for(size_t idx = 0; idx < audio_needed; idx++) {
            if (paused || audio_beeping) {
                // Do nothing
            } else if (0 == audio_cycle % AUDIO_GAP) {
                if (audio_wave >= audio_wave_ceil) {
                    audio_cycle++;
                } else {
                    audio_wave += AUDIO_SCALE;
                }
            } else if (1 == audio_cycle % AUDIO_GAP) {
                if (audio_wave == 0) {
                    audio_wave_ceil = xo_rand(AUDIO_CEILING);
                    audio_silence = 0;
                    audio_cycle++;

                } else {
                    audio_wave -= AUDIO_SCALE;
                }
            } else { // Unused
                if (audio_silence >= audio_wave_ceil) {
                    audio_wave = 0;
                    audio_silence = 0;
                    audio_cycle++;
                } else {
                    audio_silence += AUDIO_SCALE;
                }
            }

            // Convert from mono unsigned to packed stereo signed 
            uint32_t value = audio_wave;
            value = (value + (1<<15)) & 0xFFFF;
            if (audio_beeping) { // Beep even when paused
                int16_t signed_value = value;
                signed_value += (int16_t)((audio_beep_time*audio_beep_speed)%AUDIO_BEEP_VOLUME)*audio_beep_sign;
                value = (uint16_t)signed_value;
                audio_beep_time++;
                if (audio_beep_time >= AUDIO_BEEP_TIME)
                    audio_beeping = false;
            }
            apf_audio_out_write(value | (value<<16));
        }
        apf_audio_playback_en_write(1);

        // Handle controls
        uint16_t cont1_key = apf_input_cont1_key_read(); // Crop out analog sticks
        uint16_t cont1_key_edge = (~cont1_key_last) & cont1_key;
        cont1_key_last = cont1_key;

        if (cont1_key_edge & face_select) {
            paused = !paused;
        }

        if (cont1_key_edge & face_start) {
            ctrl_reset_write(1); // 1 resets entire SOC
        }

        if (cont1_key_edge & face_y) {
            winner_cut = !winner_cut;
            BEEP(AUDIO_BEEP_BASE*(winner_cut?2:4));
        }

        if (cont1_key_edge & face_x) {
            super_grow = !super_grow;
            BEEP(AUDIO_BEEP_BASE*(super_grow?4:2));
        }

        if (cont1_key_edge & face_b) {
            speed = (speed + 1) % SPEED_COUNT;
            BEEP(AUDIO_BEEP_BASE*speeds[speed][2]);
        }

        if (cont1_key_edge & face_a) {
            super_cycle = !super_cycle;
            BEEP(AUDIO_BEEP_BASE*(super_cycle?4:2));
        }

        if (cont1_key_edge & trig_l1) {
            color = xo_rotl(color, 5);
        }

        if (cont1_key_edge & trig_r1) {
            color = xo_rotr(color, 6);
        }

        // Prepare for next frame
        // Since we don't have to worry about vblank finishing, we can take our time now.
        if (!paused) { // Note we DON'T pause drawing, only updates and sound
            for(int idx = 0; idx < SHADOW_FRAMEBUFFER_SIZE; idx++)
                shadow_framebuffer[idx] = 0;
            for(int idx = 0; idx < candidates_len[current] && candidates_len[next] < candidates_max; idx++) {
                Candidate check = candidates_current[idx];
                Candidate neighbors[4] = {
                    {check.x, (check.y+1)%DISPLAY_HEIGHT},
                    {(check.x+1)%DISPLAY_WIDTH, check.y},
                    {check.x, (check.y+DISPLAY_HEIGHT-1)%DISPLAY_HEIGHT},
                    {(check.x+DISPLAY_WIDTH-1)%DISPLAY_WIDTH, check.y}
                };
                for(int n = 0; n < 4; n++) {
                    if (candidates_len[next] >= candidates_max)
                        break;
                    size_t neighbor_at = AT(neighbors[n].x, neighbors[n].y);
                    // Use the shadow framebuffer to check for pixels we've checked this frame
                    size_t neighbor_shadow_idx = neighbor_at/8;
                    uint8_t neighbor_shadow_bit = 1<<(neighbor_at%8); 
                    if (shadow_framebuffer[neighbor_shadow_idx] & neighbor_shadow_bit)
                        continue;
                    shadow_framebuffer[neighbor_shadow_idx] |= neighbor_shadow_bit;
                    uint16_t color_prev = fb[neighbor_at];
                    uint16_t color_minus_current = color-color_prev;
                    if (super_grow) {
                        color_minus_current += 0x100;
                        if (color_prev && color_minus_current < 0x200) {
                            continue;
                        }
                    } else {
                        int16_t color_minus_current_diff = color_minus_current;
                        if (color_minus_current_diff <= 0)
                            continue;
                    }
                    CANDIDATE_PUSH(neighbors[n]);
                }
            }

            // Randomize candidates list so we don't just go continually downward
            fisher_yates(candidates_next, candidates_len[next]);

            // Trick: It's really easy in this specific configuration to get "stuck",
            // so instead of resetting to 0, just hold until you get "unstuck", because it looks cool
            if (super_grow && speed == 2 && !candidates_len[next]) {
                int tmp = next;
                next = current;
                current = tmp;
            }

            candidates_len[current] = 0;
            current = next;
        } else {
            // Also randomize candidates list while paused, for cool fuzz
            fisher_yates(candidates_current, candidates_len[current]);
        }

        // Color cycle: Treat the 565 bit-packed color as a single integer. Normally, you don't want this.
        if (super_cycle) {
            color += 16;
        } else {
            color++;
        }
    }

    return 0;
}
