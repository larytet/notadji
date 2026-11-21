/* SL2: slice-based luma codec, reference model (design/32-codec-efficiency.md). */
#ifndef SL2_H
#define SL2_H
#include <stdint.h>

enum {
    SL2_T_DCT = 1,        /* integer DCT (else Walsh-Hadamard as SL1) */
    SL2_T_INTRA = 2,      /* intra modes V, H, plane (else DC only) */
    SL2_T_SUBPEL = 4,     /* quarter-pel motion (else integer vectors) */
    SL2_T_CTX = 8,        /* context-adaptive arithmetic coding (else bypass bins) */
    SL2_T_DEBLOCK = 16,   /* in-loop deblocking */
    SL2_T_RDO = 32,       /* rate-distortion decisions (else SAD rules) */
    SL2_T_ALL = 63
};

typedef struct {
    int W, H, SH;         /* picture size and slice height (multiples of 16) */
    int tools;
} sl2_cfg;

typedef struct {
    long long bins;       /* coded bins (arithmetic coder, real encodes only) */
    long long probes;     /* candidate evaluations (RDO trials) */
    long long sad_evals;  /* motion search SAD evaluations */
    long long encodes;    /* slice encodes (including rate-control probes) */
    long long kind_cnt[8]; /* real encodes: blocks skipped, inter, intra, inter with a vector difference, inter with residual, intra with residual */
    double cat_bits[8];   /* bits of the real encodes by syntax category: flags, intra mode, vector, cbf, significance, levels, dqp */
} sl2_stats;

extern sl2_stats sl2_st;
extern double sl2_tune[8];   /* encoder tuning: [0] lambda scale, [1] intra rounding, [2] inter rounding, [3] motion lambda scale */

/* Encode one slice at a fixed QP. src: whole luma frame; ref: previous reconstructed frame (NULL for an intra slice);
   recon: whole-frame buffer whose rows of this slice are written (the decoder's reconstruction after deblocking).
   dqp: one signed offset per macroblock of the picture (raster) or NULL. keep: number of scan positions kept (64 = all).
   Returns the number of bytes written to out, or -1 if cap is too small. */
int sl2_encode_slice(const sl2_cfg *cfg, const uint8_t *src, const uint8_t *ref, uint8_t *recon, int slice, int intra_slice,
                     int qp, const int8_t *dqp, int keep, uint8_t *out, int cap);

/* Encode within a byte budget: smallest QP that fits, then coefficient truncation at QP 51. Returns the size, sets *qp_out, *nenc_out. */
int sl2_encode_slice_budget(const sl2_cfg *cfg, const uint8_t *src, const uint8_t *ref, uint8_t *recon, int slice, int intra_slice,
                            int budget, const int8_t *dqp, uint8_t *out, int cap, int *qp_out, int *nenc_out);

/* Decode one slice; returns 0, or -1 on a malformed slice. ref may be NULL for an intra slice. */
int sl2_decode_slice(const sl2_cfg *cfg, const uint8_t *ref, uint8_t *recon, int slice, const uint8_t *in, int len);

/* Transform access for tests: forward/inverse 8x8 DCT (dct != 0) or Hadamard on int32 blocks (raster order, 64 values). */
void sl2_fwd(int dct, const int32_t *x, int32_t *c);
void sl2_inv(int dct, const int32_t *c, int32_t *x);

#endif
