vcpkg_download_distfile(ARCHIVE
    URLS "https://github.com/Deutsches-Klimarechenzentrum/libaec/releases/download/v${VERSION}/libaec-${VERSION}.tar.gz"
    FILENAME "libaec-github-release-v${VERSION}.tar.gz"
    SHA512 755d3ed089ebfbbdd9174eaffab7387e819dcf4a3e973d8adfa7bfac6fb07c302ab1ccd830b3771ee570daac6a4174943aee67b6f7ebd35cd10b6049e0c19b0b
)
vcpkg_extract_source_archive(SOURCE_PATH ARCHIVE "${ARCHIVE}")

string(COMPARE EQUAL "${VCPKG_LIBRARY_LINKAGE}" "static" BUILD_STATIC)
vcpkg_cmake_configure(
    SOURCE_PATH "${SOURCE_PATH}"
    OPTIONS
        -DBUILD_STATIC_LIBS=${BUILD_STATIC}
        -Dlibaec_INSTALL_CMAKEDIR=share/${PORT}
)
vcpkg_cmake_install()
vcpkg_copy_pdbs()
vcpkg_cmake_config_fixup()
vcpkg_replace_string("${CURRENT_PACKAGES_DIR}/share/libaec/libaec-config.cmake"
    "if(libaec_USE_STATIC_LIBS)"
    "if(TARGET libaec::aec OR TARGET libaec::sz)\nelseif(\"${BUILD_STATIC}\") # forced by vcpkg"
)
file(REMOVE_RECURSE "${CURRENT_PACKAGES_DIR}/debug/include")
file(INSTALL "${CURRENT_PORT_DIR}/usage" DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")
vcpkg_install_copyright(FILE_LIST "${SOURCE_PATH}/LICENSE.txt")
