#!/usr/bin/env python
import logging

import citrix
import numpy as np

from scipy.ndimage import morphology
from dipy.tracking import utils

def read_labels_file(labels_file):
    ''' Returns a dictionary with the labels as keys and which structure
        they represent as value '''
    label2structure = {}
    with open(labels_file) as f:
        for line in f:
            label, struc = line.split()[:2]
            label = int(label)

            label2structure[label] = struc

    return label2structure

def seeds_from_labeled_volume(labeled_volume_file, labels_file,
                              seeds_per_voxel, outfile, mask_file=None,
                              vx_expand=0, only_border=True, vol_out=None,
                              verbose=0):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    # Extract map labels -> structures
    label2structure = read_labels_file(labels_file)

    # Load volume with labels
    labels_nifti = citrix.load(labeled_volume_file)
    labels_volume = np.round(labels_nifti.get_fdata()).astype(int)
    labels_affine = labels_nifti.affine

    # Load mask if any
    if mask_file:
        mask = citrix.load(mask_file).get_data().astype(bool)
    else:
        mask = None

    # Create header of the output file
    txtheader = "#ModelType BrainStructure Vox_i Vox_j Vox_k Seeding_Points \n"
    with open(outfile, 'w') as f:
        f.write(txtheader)

    # Create seeds from voxels
    seed_volume = np.zeros_like(labels_volume)  # Visual confirmation
    text = ""
    label_and_nonzero = []  # Stores tuples (label, nonzero)
    for label in label2structure:
        label_mask = labels_volume == label

        # We dilate the structure *vx_expand* times, which could be zero
        if vx_expand:
            seed_structure = morphology.binary_dilation(label_mask, None,
                                                        vx_expand)
        else:
            seed_structure = label_mask

        if only_border:
            # erode the structure one time and substract to get the border
            eroded_structure = morphology.binary_erosion(label_mask)
            seed_structure = np.bitwise_xor(seed_structure, eroded_structure)

        # Intersect with the mask
        if mask is not None:
            seed_structure = np.multiply(seed_structure, mask)
        nzr = seed_structure.nonzero()
        label_and_nonzero.append((label, nzr))

    # We sort them so the small structures can survive
    label_and_nonzero.sort(key=lambda t: len(t[1]), reverse=True)
    for label, nzr in label_and_nonzero:
        seed_volume[nzr] = label

    for label in label2structure:
        logging.debug('Procesing label: {}'.format(label))
        seed_structure = (seed_volume == label)
        nzr = seed_structure.nonzero()
        nzr_positions = np.transpose(nzr)
        # Create seeds randomly distributed inside of each voxel
        label_seeds = utils.random_seeds_from_mask(mask=seed_structure,
                                                   seeds_count=seeds_per_voxel,
                                                   affine=labels_affine)
        # Add information to the output file
        structure_name = label2structure[label]
        for s, (i, j, k) in enumerate(nzr_positions):
            # Take the seed points for this voxel
            li, ls = s*seeds_per_voxel, s*seeds_per_voxel + seeds_per_voxel
            spoints = label_seeds[li:ls]
            ptxt = " ".join("{} {} {}".format(x, y, z) for x, y, z in spoints)
            # Add them to the text
            text += "CIFTI_MODEL_TYPE_VOXELS {} {} {} {} {}\n".format(
                structure_name, i, j, k, ptxt)

    with open(outfile, 'a') as f:
        f.write(text)

    # Save just for visual confirmation
    if vol_out:
        citrix.save(vol_out, seed_volume, labels_nifti.header,
                    labels_nifti.affine, version=1)
