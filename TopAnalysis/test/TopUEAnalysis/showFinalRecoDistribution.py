import ROOT
import os
import sys
import optparse
import pickle
from collections import OrderedDict,defaultdict
import pprint

from UEPlot import *
from UESummaryPlotCommon import *

"""
"""
def buildUEPlot(obsAxis,sliceAxis,regions,fIn,fSyst):

    obs        = obsAxis.GetName().split('_')[0]
    sliceVar   = sliceAxis.GetName().split('_')[0] if sliceAxis else None
    nSliceBins = 1+sliceAxis.GetNbins()            if sliceAxis else 1

    for r in regions:

        plotsPerRegion=[]
        for i in xrange(0,nSliceBins):

            nomKey='%s_%s_%d_%s_None_True'%(obs,sliceVar,i,r)

            uePlots={}

            #collect different comparison sets
            for icomp in xrange(0,len(COMPARISONSETS)):
                compSet, compVarList = COMPARISONSETS[icomp]
                ci, marker, fill     = PLOTFORMATS[icomp]
                uePlots[compSet]     = UEPlot(nomKey+'_mc%d'%icomp,compSet, ci, marker,fill , obsAxis)
                
                for compVarName,varList in compVarList:

                    #get the different MCs variations
                    for varName in varList:
                        hvar=fIn.Get('%s/%s_%s'%(nomKey,nomKey,varName))
                        try :
                            hvar.GetNbinsX()
                        except:
                            hvar=fSyst.Get('%s/%s_%s'%(nomKey,nomKey,varName))
                        uePlots[compSet].addVariation(varName,
                                                      None if compVarName=='nominal' else 'th',
                                                      hvar)
                    
                    #for the nominal MC get the associated exp uncertainties
                    if compVarName!='nominal' : continue
                    mcDataSetName=varList[0]
                    expSystsKey=nomKey.replace('None_True','syst_True')
                    expSystsH=fIn.Get('%s/%s_%s'%(expSystsKey,expSystsKey,mcDataSetName))
                    try:
                        expSystsH.GetNbinsX()
                    except:
                        expSystsH=fSyst.Get('%s/%s_%s'%(expSystsKey,expSystsKey,mcDataSetName))

                    #project new histograms for each variation
                    for ybin in xrange(2,expSystsH.GetNbinsY()):
                        h=expSystsH.ProjectionX('px',ybin,ybin)

                        varName=expSystsH.GetYaxis().GetBinLabel(ybin)
                        if varName[-2:] in ['up','dn']  : varName=varName[:-2]
                        varType='exp'
                        if varName in ['mur','muf','q'] :                    
                            varName='ME scale'
                            varType='th'
                        elif varName in ['p_{T}(t)']:
                            varName='toppt'
                            varType='th'

                        #skip special theory unc. based on re-weighting if not the first sample
                        if icomp!=0 and varType=='th': continue
                        uePlots[compSet].addVariation(varName,'exp',h)

            #add the data
            t=fIn.Get(nomKey)
            data,bkg=None,None
            for pkey in t.GetListOfKeys():
                h=t.Get(pkey.GetName())
                if not h.InheritsFrom('TH1') : continue
                if 'Data' in h.GetTitle()     : data=pkey.ReadObj()
                elif not h.GetTitle()==COMPARISONSETS[0][1][0][1][0]:
                    if bkg is None : bkg=h.Clone('bkg')
                    else           : bkg.Add(h)

            #subtract the background from the data
            try:
                data.Add(bkg,-1)
                bkg.Delete()
            except:
                pass

            uePlots['Data']=UEPlot(nomKey+'_data', obs, 1,             1, 0,    obsAxis) 
            uePlots['Data'].addVariation('Data',None,data)

            plotsPerRegion.append( uePlots )

        #
        showUEPlots(uePlots,opt.outDir)

"""
"""
def readPlotsFrom(args,opt):

    #analysis axes
    analysisaxis=None
    with open(opt.analysisAxis,'r') as cachefile:
        analysisaxis = pickle.load(cachefile)

    #open input files
    fIn=ROOT.TFile.Open(args[0])
    fSyst=ROOT.TFile.Open(args[1]) if len(args)>1 else None


    #build and show the different plot combinations (observables vs slices)
    for obs in OBSERVABLES:

        obsAxis=analysisaxis[(obs,True)]
        
        for s in SLICES:

            sliceAxis=None 
            regions=['inc']
            if not s is None:
                sliceAxis = analysisaxis[(s,False)]
                if s in EVAXES and obs in ['chmult','chavgpt','chflux']: regions += [0,1,2]
                if s =='chmult' and not obs in ['chavgpt','chflux'] : continue
             
            buildUEPlot(obsAxis,sliceAxis,regions,fIn,fSyst)


"""
"""
def main():

    ROOT.gStyle.SetOptStat(0)
    ROOT.gStyle.SetOptTitle(0)
    ROOT.gROOT.SetBatch(True)

    #configuration
    usage = 'usage: %prog [options]'
    parser = optparse.OptionParser(usage)
    parser.add_option('--cfg',
                      dest='analysisAxis',
                      help='cfg with axis definitions [%default]',
                      type='string',
                      default='%s/src/TopLJets2015/TopAnalysis/UEanalysis/analysisaxiscfg.pck'%os.environ['CMSSW_BASE'])
    parser.add_option('--out',
                      dest='outDir',
                      help='output directory [%default]',
                      type='string',
                      default='UEanalysis/analysis/plots/reco')
    (opt, args) = parser.parse_args()

    os.system('mkdir -p %s'%opt.outDir)

    readPlotsFrom(args,opt)



"""
for execution from another script
"""
if __name__ == "__main__":
    sys.exit(main())
