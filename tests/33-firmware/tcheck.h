/* minimal check harness for the host tests */
#ifndef TCHECK_H
#define TCHECK_H
#include <stdio.h>
#include <stdlib.h>
static int tc_fail, tc_n;
#define CHECK(c) do { tc_n++; if (!(c)) { tc_fail++; printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define CHECK_EQ(a, b) do { long long _a = (long long)(a), _b = (long long)(b); tc_n++; if (_a != _b) { tc_fail++; \
    printf("  FAIL %s:%d: %s == %s (%lld vs %lld)\n", __FILE__, __LINE__, #a, #b, _a, _b); } } while (0)
#define TEST(name) static void name(void)
#define RUN(name) do { int _f = tc_fail; name(); printf("  %s  %s\n", tc_fail == _f ? "pass" : "FAIL", #name); } while (0)
#define TC_DONE() do { printf("%s: %d checks, %d failed\n", __FILE__, tc_n, tc_fail); return tc_fail ? 1 : 0; } while (0)
/* xorshift generator for random tests */
static unsigned long long tc_rs = 88172645463325252ull;
static inline unsigned long long tc_rand(void) { tc_rs ^= tc_rs << 13; tc_rs ^= tc_rs >> 7; tc_rs ^= tc_rs << 17; return tc_rs; }
#endif
