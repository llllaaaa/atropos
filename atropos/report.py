# coding: utf-8
"""Routines for printing a report.
"""
import sys
import textwrap
from atropos.adapters import BACK, FRONT, PREFIX, SUFFIX, ANYWHERE, LINKED

# TODO:
# * Refactor: Text report generated using template engine
#   * This module generates report from dict
#   * Reliably line things up in columns.
#   * Fix https://github.com/marcelm/cutadapt/issues/128
# * Enhancements:
#   * Integrate with MultiQC
#

def print_report(options, wallclock_time, cpu_time, stats, trimmer_classes):
    outfile = options.report_file
    close = False
    
    if outfile is not None:
        outfile = open(outfile, "w")
        close = True
    elif not options.quiet:
        outfile = sys.stderr if options.output is None else sys.stdout
    else:
        return None
    
    paired = options.paired
    stats["paired"] = paired
    stats["wallclock_time"] = max(wallclock_time, 0.01)
    stats["cpu_time"] = max(cpu_time, 0.01)
    stats['pairs_or_reads'] = "Pairs" if paired else "Reads"
    
    try:
        # TODO: rewrite generate_report so that this call
        # receives a string result and writes it to outfile
        # outfile.write(generate_report(paired, time, stats))
        generate_report(stats, trimmer_classes, outfile)
        return stats
    finally:
        if close and outfile is not None:
            outfile.close()
    
        # def get_values(self):
        #	values = var(self)
        #	return values

def generate_report(stats, trimmer_classes, outfile):
    def _print(*args, **kwargs): print(*args, file=outfile, **kwargs)
    
    ADAPTER_TYPES = {
        BACK: "regular 3'",
        FRONT: "regular 5'",
        PREFIX: "anchored 5'",
        SUFFIX: "anchored 3'",
        ANYWHERE: "variable 5'/3'",
        LINKED: "linked",
    }
    
    def print_error_ranges(adapter_length, error_rate):
        _print("No. of allowed errors:")
        prev = 0
        for errors in range(1, int(error_rate * adapter_length) + 1):
            r = int(errors / error_rate)
            _print("{0}-{1} bp: {2};".format(prev, r - 1, errors - 1), end=' ')
            prev = r
        if prev == adapter_length:
            _print("{0} bp: {1}".format(adapter_length, int(error_rate * adapter_length)))
        else:
            _print("{0}-{1} bp: {2}".format(prev, adapter_length, int(error_rate * adapter_length)))
        _print()

    def print_histogram(d, adapter_length, n, error_rate, errors):
        """
        Print a histogram. Also, print the no. of reads expected to be
        trimmed by chance (assuming a uniform distribution of nucleotides in the reads).
        d -- a dictionary mapping lengths of trimmed sequences to their respective frequency
        adapter_length -- adapter length
        n -- total no. of reads.
        """
        h = []
        for length in sorted(d):
            # when length surpasses adapter_length, the
            # probability does not increase anymore
            estimated = n * 0.25 ** min(length, adapter_length)
            h.append( (length, d[length], estimated) )
        
        def errs_to_str(l, e):
            if e in errors[l]:
                return str(errors[l][e])
            return "0"
        
        _print("length", "count", "expect", "max.err", "error counts", sep="\t")
        for length, count, estimate in h:
            max_errors = max(errors[length].keys())
            errs = ' '.join(errs_to_str(length, e) for e in range(max_errors+1))
            _print(length, count, "{0:.1F}".format(estimate),
                   int(error_rate*min(length, adapter_length)), errs, sep="\t")
        _print()

    def print_adjacent_bases(bases, sequence):
        """
        Print a summary of the bases preceding removed adapter sequences.
        Print a warning if one of the bases is overrepresented and there are
        at least 20 preceding bases available.

        Return whether a warning was printed.
        """
        total = sum(bases.values())
        if total == 0:
            return False
        _print('Bases preceding removed adapters:')
        warnbase = None
        for base in ['A', 'C', 'G', 'T', '']:
            b = base if base != '' else 'none/other'
            fraction = 1.0 * bases[base] / total
            _print('  {0}: {1:.1%}'.format(b, fraction))
            if fraction > 0.8 and base != '':
                warnbase = b
        if total >= 20 and warnbase is not None:
            _print('WARNING:')
            _print('	The adapter is preceded by "{0}" extremely often.'.format(warnbase))
            _print('	The provided adapter sequence may be incomplete.')
            _print('	To fix the problem, add "{0}" to the beginning of the adapter sequence.'.format(warnbase))
            _print()
            return True
        _print()
        return False
    
    #----------------
    
    """Print report to standard output."""
    if stats["N"] == 0:
        _print("No reads processed! Either your input file is empty or you used the wrong -f/--format parameter.")
        return
    _print("Wallclock time: {0:.2F} s ({1:.0F} us/read; {2:.2F} M reads/minute).".format(
        stats["wallclock_time"], 1E6 * stats["wallclock_time"] / stats["N"], stats["N"] / stats["wallclock_time"] * 60 / 1E6))
    _print("CPU time (main process): {0:.2F} s".format(stats["cpu_time"]))
    
    report = "\n=== Summary ===\n\n"
    if stats["paired"]:
        report += textwrap.dedent("""\
        Total read pairs processed:		 {N:13,d}
          Read 1 with adapter:			 {with_adapters[0]:13,d} ({with_adapters_fraction[0]:.1%})
          Read 2 with adapter:			 {with_adapters[1]:13,d} ({with_adapters_fraction[1]:.1%})
        """)
    else:
        report += textwrap.dedent("""\
        Total reads processed:			 {N:13,d}
        Reads with adapters:			 {with_adapters[0]:13,d} ({with_adapters_fraction[0]:.1%})
        """)
    if stats["too_short"] is not None:
        report += "{pairs_or_reads} that were too short:		   {too_short:13,d} ({too_short_fraction:.1%})\n"
    if stats["too_long"] is not None:
        report += "{pairs_or_reads} that were too long:			   {too_long:13,d} ({too_long_fraction:.1%})\n"
    if stats["too_many_n"] is not None:
        report += "{pairs_or_reads} with too many N:			   {too_many_n:13,d} ({too_many_n_fraction:.1%})\n"
    
    report += textwrap.dedent("""\
    {pairs_or_reads} written (passing filters):			{written:13,d} ({written_fraction:.1%})
    """)
    
    if "corrected" in stats:
        report += "Pairs corrected:			{corrected:13,d} ({corrected_fraction:.1%})\n"
    
    report += "\nTotal basepairs processed:			{total_bp:13,d} bp\n"
    
    if stats["paired"]:
        report += "	 Read 1: {total_bp1:13,d} bp\n"
        report += "	 Read 2: {total_bp2:13,d} bp\n"
    
    for modifier_class in trimmer_classes:
        name = modifier_class.__name__
        if stats[name] > 0:
            spacing = ' ' * (40 - len(modifier_class.display_str))
            report += "{0}:{1}{{{2}:13,d}} bp ({{{2}_fraction:.1%}})\n".format(modifier_class.display_str, spacing, name)
            if stats["paired"]:
                report += "	 Read 1: {{{}_bp[0]:13,d}} bp\n".format(name)
                report += "	 Read 2: {{{}_bp[1]:13,d}} bp\n".format(name)
    
    report += "Total written (filtered):                {total_written_bp:13,d} bp ({total_written_bp_fraction:.1%})\n"
    if stats["paired"]:
        report += "	 Read 1: {written_bp[0]:13,d} bp\n"
        report += "	 Read 2: {written_bp[1]:13,d} bp\n"
    
    if "corrected" in stats:
        report += "Total corrected bp:                        {total_corrected_bp:13,d} ({total_corrected_bp_fraction:.1%})\n"
        report += "	 Read 1:                {corrected_bp[0]:13,d} ({corrected_bp_fraction[0]:.1%})\n"
        report += "	 Read 2:                {corrected_bp[1]:13,d} ({corrected_bp_fraction[1]:.1%})\n"
    
    _print(report.format(**stats))
    
    warning = False
    for which_in_pair in (0, 1):
        for adapter in stats["adapters"][which_in_pair]:
            if stats["paired"]:
                extra = 'First read: ' if which_in_pair == 0 else 'Second read: '
            else:
                extra = ''

            _print("=" * 3, extra + "Adapter", adapter["name"], "=" * 3)
            _print()
            if adapter["where"] == LINKED:
                _print("Sequence: {0}...{1}; Type: linked; Length: {2}+{3}; Trimmed: {4} times; Half matches: {5}".
                    format(
                        adapter["front_sequence"],
                        adapter["back_sequence"],
                        len(adapter["front_sequence"]),
                        len(adapter["back_sequence"]),
                        adapter["total_front"], adapter["total_back"]
                    ))
            else:
                _print("Sequence: {0}; Type: {1}; Length: {2}; Trimmed: {3} times.".
                    format(adapter["sequence"], ADAPTER_TYPES[adapter["where"]],
                        len(adapter["sequence"]), adapter["total"]))
    
            if adapter["total"] == 0:
                _print()
                continue
            if adapter["where"] == ANYWHERE:
                _print(adapter["total_front"], "times, it overlapped the 5' end of a read")
                _print(adapter["total_back"], "times, it overlapped the 3' end or was within the read")
                _print()
                print_error_ranges(len(adapter["sequence"]), adapter["max_error_rate"])
                _print("Overview of removed sequences (5')")
                print_histogram(adapter["lengths_front"], len(adapter["sequence"]), stats["N"],
                    adapter["max_error_rate"], adapter["errors_front"])
                _print()
                _print("Overview of removed sequences (3' or within)")
                print_histogram(adapter["lengths_back"], len(adapter["sequence"]), stats["N"],
                    adapter["max_error_rate"], adapter["errors_back"])
            elif adapter["where"] == LINKED:
                _print()
                print_error_ranges(len(adapter["front_sequence"]), adapter["front_max_error_rate"])
                print_error_ranges(len(adapter["back_sequence"]), adapter["back_max_error_rate"])
                _print("Overview of removed sequences at 5' end")
                print_histogram(adapter["front_lengths_front"], len(adapter["front_sequence"]),
                    stats["N"], adapter["front_max_error_rate"], adapter["front_errors_front"])
                _print()
                _print("Overview of removed sequences at 3' end")
                print_histogram(adapter["back_lengths_back"], len(adapter["back_sequence"]),
                    stats["N"], adapter["back_max_error_rate"], adapter["back_errors_back"])
            elif adapter["where"] in (FRONT, PREFIX):
                _print()
                print_error_ranges(len(adapter["sequence"]), adapter["max_error_rate"])
                _print("Overview of removed sequences")
                print_histogram(adapter["lengths_front"], len(adapter["sequence"]),
                    stats["N"], adapter["max_error_rate"], adapter["errors_front"])
            else:
                assert adapter["where"] in (BACK, SUFFIX)
                _print()
                print_error_ranges(len(adapter["sequence"]), adapter["max_error_rate"])
                warning = warning or print_adjacent_bases(adapter["adjacent_bases"], adapter["sequence"])
                _print("Overview of removed sequences")
                print_histogram(adapter["lengths_back"], len(adapter["sequence"]),
                    stats["N"], adapter["max_error_rate"], adapter["errors_back"])
    
    if warning:
        _print('WARNING:')
        _print('	One or more of your adapter sequences may be incomplete.')
        _print('	Please see the detailed output above.')
