import sys
import re
import os.path
import argparse
import subprocess
import json
from Bio import codonalign
from p3_allan import patric_api
from p3_allan import phylocode

parser = argparse.ArgumentParser()
parser.add_argument("genomeIdsFile", type=str, help="file with PATRIC genome IDs, one per line, optional content after tab delimiter ignored")
parser.add_argument("--genomeObjectFile", metavar="file", type=str, help="genome object (json file) to be added to ingroup")
parser.add_argument("--outgroupIdsFile", metavar="file", type=str, help="ougroup genome ids, one per line (or first column of TSV)")
parser.add_argument("--maxGenes", metavar="#", type=int, default=50, help="maximum number of genes in concatenated alignment [50]")
parser.add_argument("--bootstrapReps", metavar="#", type=int, default=0, help="number of raxml 'fast boostrap' replicates [0]")
parser.add_argument("--maxGenomesMissing", metavar="#", type=int, default=0, help="maximum number of ingroup genomes missing a member of any homolog group")
parser.add_argument("--maxAllowedDups", metavar="maxDups", type=int, default=0, help="maximum duplicated gene occurrences within ingroup genomes for homolog to be included [0]")
parser.add_argument("--endGapTrimThreshold", metavar="maxPropGaps", type=float, default=0.5, help="stringency of end-gap trimming, lower for less trimming [0.5]")
parser.add_argument("--raxmlExecutable", metavar="program_name", type=str, default="raxml", help="name of program to call (possibly with path)[raxml]")
parser.add_argument("--rateModel", metavar="rateModel", type=str, choices = ['CAT', 'GAMMA'], default="CAT", help="variable rate category model CAT|GAMMA [CAT]")
parser.add_argument("--proteinModel", metavar="substModel", type=str, default="WAGF", help="raxml protein substitution model [WAGF]")
parser.add_argument("--analyzeCodons", action='store_true', help="set this flag to analyze codons")
parser.add_argument("--analyzeProteins", action='store_true', help="set this flag to analyze proteins")
#parser.add_argument("--analyzeBoth", action='store_true', help="set this flag to analyze both codons and proteins")
parser.add_argument("--raxmlNumThreads", metavar="T", type=int, default=1, help="number of threads for raxml [1]")
parser.add_argument("--runRaxml", action='store_true', help="Deprecated: raxml run by default, use 'deferRaxml' to turn off")
parser.add_argument("--deferRaxml", action='store_true', help="set this flag if you do not want raxml to be run automatically (you can run it manually later using the command file provided)")
parser.add_argument("--outputDirectory", type=str, metavar="out_dir", help="directory for output, create if it does not exist")
parser.add_argument("--debugMode", action='store_true', help="turns on progress output to stderr")
#parser.add_argument("--enableGenomeGenePgfamFileReuse", action='store_true', help="read genes and pgfams from stored file matching genomeIdsFile if it exists")
args = parser.parse_args()

subprocess.check_call(['which', args.raxmlExecutable])
phylocode.checkMuscle()

genomeIds = []
with open(args.genomeIdsFile) as F:
    for line in F:
        m = re.match(r"(\d+\.\d+)", line)
	if m:
            genomeIds.append(m.group(1))
if args.debugMode:
    sys.stderr.write("got %d genomeIds\n%s\n"%(len(genomeIds), "\t".join(genomeIds)))
    if args.genomeObjectFile:
        sys.stderr.write("also genome object file: %s\n"%args.genomeObjectFile)

outgroupIds = []
if args.outgroupIdsFile:
    with open(args.outgroupIdsFile) as F:
        for line in F:
            m = re.match(r"(\d+\.\d+)", line)
	    if m:
                outgroupIds.append(m.group(1))
if args.debugMode:
    sys.stderr.write("got % outgroupIds\n%s\n"%(len(outgroupIds), "\t".join(outgroupIds)))

if len(genomeIds) + len(outgroupIds) < 4:
    sys.stderr.write("too few genomeIds to build a tree with: %d"%(len(genomeIds)+len(outgroupIds)))
    sys.exit(1)

fileBase = os.path.basename(args.genomeIdsFile)
fileBase = re.sub("\..*", "", fileBase)

# if either codons or proteins is specified, analyze just that, otherwise analyze both
if not (args.analyzeCodons or args.analyzeProteins):
    args.analyzeCodons = args.analyzeProteins = True

if not args.outputDirectory:
    args.outputDirectory=fileBase+"_dir/"
if not args.outputDirectory.endswith("/"):
    args.outputDirectory += "/"
if os.path.exists(args.outputDirectory):
    sys.stdout.write("data directory %s exists, may overwrite data\n"%args.outputDirectory)
else:
    os.mkdir(args.outputDirectory)

patric_api.debug = args.debugMode
phylocode.debug = args.debugMode

# this is where we gather the list of Pgfam genes for each ingroup genome ID
genomeGenePgfamList=[]
if os.path.isfile(args.outputDirectory+fileBase+".genomeGenePgfams.txt"):
    with open(args.outputDirectory+fileBase+".genomeGenePgfams.txt") as F:
        for line in F:
            if "genome" in line:
                continue # header
            row = line.rstrip("\n").split("\t")
            if len(row) == 3:
                genomeGenePgfamList.append(row)
else:
    genomeGenePgfamList = patric_api.getPatricGenesPgfamsForGenomeList(genomeIds)

genomeObject=None
genomeObject_genomeId=None
if args.genomeObjectFile:
    #try:
        genomeObject = json.load(open(args.genomeObjectFile))
        genomeObjectGenePgfams = patric_api.getPatricGenesPgfamsForGenomeObject(genomeObject)
        genomeGenePgfamList.extend(genomeObjectGenePgfams)
        genomeObject_genomeId = genomeObjectGenePgfams[0][0]
        genomeIds.append(genomeObject_genomeId)
        if args.debugMode:
            sys.stderr.write("parsed json file %s, got PGFam genes=%d, total now is %d\n"%(args.genomeObjectFile, len(genomeObjectGenePgfams), len(genomeGenePgfamList)))
    #except Exception as e:
        #sys.stderr.write("Problem reading genome object json file.\n%s\n"%str(e))

# add outgroup genes+pgfams to list, get dynamically as the outgroup might change from run to run
if len(outgroupIds):
    genomeGenePgfamList.extend(patric_api.getPatricGenesPgfamsForGenomeList(outgroupIds))

with open(args.outputDirectory+fileBase+".genomeGenePgfams.txt", 'w') as F:
    for row in genomeGenePgfamList:
        F.write("\t".join(row)+"\n")

if args.debugMode:
    sys.stderr.write("got genes and pgfams for genomes, len=%d\n"%len(genomeGenePgfamList))
    for row in genomeGenePgfamList[:1]:
        sys.stderr.write("\t".join(row)+"\n")
if not len(genomeGenePgfamList):
    sys.stderr.write("got no genes and pgfams for genomes, exiting\n")
    sys.exit(1)

if args.debugMode:
    sys.stderr.write("allowing %d genomes missing per PGfam of ingroup (out of %d total)\n"%(args.maxGenomesMissing, len(genomeIds)))
if args.maxGenomesMissing >= len(genomeIds):
    raise Exception("getSingleCopyPgfams: maxGenomesMissing too large: %d"%args.maxGenomesMissing)

# call to getSingleCopyPgfams uses ingroup taxa, outgroup is not involved in selecting single copy pgfams
singleCopyPgfams = phylocode.selectSingleCopyPgfams(genomeGenePgfamList, genomeIds, maxGenomesMissing=args.maxGenomesMissing, maxAllowedDups=args.maxAllowedDups)

if args.debugMode:
    sys.stderr.write("got single copy pgfams, num=%d\n"%len(singleCopyPgfams))
if len(singleCopyPgfams) > args.maxGenes:
    singleCopyPgfams=singleCopyPgfams[0:args.maxGenes]
    if args.debugMode:
        sys.stderr.write("\tselecting top single-family genes: %d\n"%len(singleCopyPgfams))
if not len(singleCopyPgfams):
    sys.stderr.write("got no single copy pgfams, exiting\n")
    sys.exit(1)
with open(args.outputDirectory+fileBase+".singlishCopyPgfams.txt", 'w') as F:
    for pgfam in singleCopyPgfams:
        F.write(pgfam+"\n")

allGenomeIds = genomeIds
allGenomeIds.extend(outgroupIds)
#genesForPgfams = phylocode.getGenesForPgfams(genomeGenePgfamList, allGenomeIds, singleCopyPgfams)
genesForPgfams={}
for pgfam in singleCopyPgfams:
    genesForPgfams[pgfam] = []
genomeObjectGeneDna={}
genomeObjectGenes=set()
numGenesAdded=0
for row in genomeGenePgfamList:
    genome, gene, pgfam = row
    if genome in allGenomeIds and pgfam in genesForPgfams:
        genesForPgfams[pgfam].append(gene)
        if genome == genomeObject_genomeId:
            genomeObjectGenes.add(gene)
        numGenesAdded += 1

if args.debugMode:
    sys.stderr.write("got %d genes for %d pgfams\n"%(numGenesAdded, len(genesForPgfams)))
    for pgfamId in singleCopyPgfams: #genesForPgfams:
        if pgfamId not in genesForPgfams:
            sys.stderr.write("singleCopy pgfamId %s not in genesForPgfams\n"%pgfamId)
            continue
if genomeObject:
    genomeObjectProteins = patric_api.getGenomeObjectProteins(genomeObjectGenes, genomeObject)
    genomeObjectGeneDna = patric_api.getGenomeObjectGeneDna(genomeObjectGenes, genomeObject)

proteinAlignments = {}
codonAlignments = {}
#phylocode.generateAlignmentsForCodonsAndProteins(genesForPgfams, proteinAlignments, codonAlignments)
for pgfamId in genesForPgfams: #genesForPgfams:
    proteinSeqRecords = patric_api.getProteinBioSeqRecordsForPatricIds(genesForPgfams[pgfamId])
    if args.genomeObjectFile:
        for geneId in genesForPgfams[pgfamId]:
            if geneId in genomeObjectProteins:
                proteinSeqRecords.append(genomeObjectProteins[geneId])
    proteinAlignment = phylocode.alignSeqRecordsMuscle(proteinSeqRecords)
    proteinAlignment = phylocode.resolveDuplicatesPerPatricGenome(proteinAlignment)
    proteinAlignment.sort()
    codonAlignment = phylocode.proteinToCodonAlignment(proteinAlignment, genomeObjectGeneDna)
    if codonAlignment: # if an error happened, we don't do next steps
        phylocode.relabelSequencesByGenomeId(codonAlignment)
        if codonAlignment.get_alignment_length() % 3:
            raise Exception("codon alignment length not multiple of 3 for %s\n"%pgfamId)
        codonAlignments[pgfamId] = codonAlignment
    phylocode.relabelSequencesByGenomeId(proteinAlignment)
    proteinAlignments[pgfamId] = proteinAlignment

sys.stderr.write("protein and codon alignments completed. num prot als = %d, num codon als = %d\n"%(len(proteinAlignments), len(codonAlignments)))
sys.stdout.write("First prot alignment has %d elements\n"%len(proteinAlignments.values()[0]))
sys.stdout.write("original_id of first prot: %s\n"%proteinAlignments.values()[0][0].annotations['original_id'])
phylocode.trimAlignments(proteinAlignments, args.endGapTrimThreshold)
sys.stdout.write("original_id of first prot: %s\n"%proteinAlignments.values()[0][0].annotations['original_id'])
phylocode.trimAlignments(codonAlignments, args.endGapTrimThreshold)

numTaxa=0
for pgfamId in proteinAlignments:
    numTaxa = max(numTaxa, len(proteinAlignments[pgfamId]))

# generate hopefully uniq output file name base
phyloFileBase = fileBase+"_%dtaxa"%(numTaxa)
if args.analyzeCodons:
    phyloFileBase += "_%scds"%len(codonAlignments)
if args.analyzeProteins:
    phyloFileBase += "_%sproteins"%len(proteinAlignments)

proteinPositions=0
codonPositions = 0
# write the genes included in each homology group (and those paralogs excluded)
with open(args.outputDirectory+phyloFileBase+".pgfamsAndGenesIncludedInAlignment.txt", 'w') as F:
    for pgfamId in singleCopyPgfams:
        if pgfamId in genesForPgfams:
            if pgfamId in proteinAlignments:
                proteinPositions += proteinAlignments[pgfamId].get_alignment_length()
                genesNotIncluded = set(genesForPgfams[pgfamId])
                genesIncluded = set()
                F.write(pgfamId+"\tProteins\t")
                for seqRecord in proteinAlignments[pgfamId]:
                    originalId = seqRecord.annotations['original_id']
                    F.write("\t"+originalId)
                    genesNotIncluded.remove(originalId)
                    genesIncluded.add(originalId)
                if len(genesNotIncluded):
                    F.write("\tdeletedParalogs: \t"+"\t".join(genesNotIncluded))
                F.write("\n")
                if pgfamId in codonAlignments:
                    F.write(pgfamId+"\tCodons\t")
                    codonPositions += codonAlignments[pgfamId].get_alignment_length()
                    for seqRecord in codonAlignments[pgfamId]:
                        originalId = seqRecord.annotations['original_id']
                        F.write("\t"+originalId)
                        genesIncluded.remove(originalId)
                    if len(genesIncluded):
                        F.write("\tlackingCodonAlignment: \t"+"\t".join(genesIncluded))
                    F.write("\n")
                else:
                    F.write(pgfamId+"\nNo codon alignment\n")
            else:
                F.write(pgfamId+"\tNo protein alignment\n")
        else:
            F.write(pgfamId+" has no genes selected")
        F.write("\n")
    F.close()

# finally, output concatenated protein and/or DNA alignment and partitions and raxml command to appropriate files
raxmlCommand=''
if args.analyzeProteins and args.analyzeCodons:
    phyloFileBase += "_codonAndProteins"
    phylocode.outputCodonsProteinsPhylip(codonAlignments, proteinAlignments, args.outputDirectory+phyloFileBase+".phy")
    with open(args.outputDirectory+phyloFileBase+".partitions", 'w') as PartitionFile:
        for i in range(1,4):
            PartitionFile.write("DNA, codon%d = %d-%d\\3\n"%(i, i, codonPositions))
        PartitionFile.write("%s, proteins = %d-%d\n"%(args.proteinModel, codonPositions+1, codonPositions+proteinPositions))
    raxmlCommand = [args.raxmlExecutable, "-s", phyloFileBase+".phy", "-n", phyloFileBase, "-m",  "GTR%s"%args.rateModel, "-q",  phyloFileBase+".partitions",  "-p", "12345", "-T", str(args.raxmlNumThreads)]

elif args.analyzeCodons:
    phyloFileBase += "_codonAlignment"
    phylocode.writeConcatenatedAlignmentsPhylip(codonAlignments, args.outputDirectory+phyloFileBase+".phy")
    with open(args.outputDirectory+phyloFileBase+".partitions", 'w') as PartitionFile:
        for i in range(1,4):
            PartitionFile.write("DNA, codon%d = %d-%d\\3\n"%(i, i, codonPositions))
    raxmlCommand = [args.raxmlExecutable, "-s", phyloFileBase+".phy", "-n", phyloFileBase, "-m",  "GTR%s"%args.rateModel, "-q",  phyloFileBase+".partitions",  "-p", "12345", "-T", str(args.raxmlNumThreads)]

elif args.analyzeProteins:
    phyloFileBase += "_proteinAlignment"
    phylocode.writeConcatenatedAlignmentsPhylip(proteinAlignments, args.outputDirectory+phyloFileBase+".phy")
    raxmlCommand = [args.raxmlExecutable, "-s", phyloFileBase+".phy", "-n", phyloFileBase, "-m",  "PROT%s%s"%(args.rateModel, args.proteinModel), "-p", "12345", "-T", str(args.raxmlNumThreads)]

if args.bootstrapReps > 0:
    raxmlCommand.extend(["-f", "a", "-x", "12345", "-N", str(args.bootstrapReps)]) 
with open(args.outputDirectory+phyloFileBase+".raxmlCommand.sh", 'w') as F:
    F.write(" ".join(raxmlCommand)+"\n")

if not args.deferRaxml:
    subprocess.Popen(raxmlCommand, cwd=args.outputDirectory)

sys.stderr.write("analysis output written to directory %s\n"%args.outputDirectory)
sys.stdout.write("\n") 
